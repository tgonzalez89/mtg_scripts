from __future__ import annotations

import gzip
import json
import sqlite3
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest

from mtg_scripts.services.scryfall import store

if TYPE_CHECKING:
    from pathlib import Path


def _printing(print_id: str, *, set_code: str, updated: str) -> dict[str, Any]:
    return {
        "id": print_id,
        "oracle_id": "oracle-fetchland",
        "name": "Fetch Land",
        "set": set_code,
        "set_name": "Test Set",
        "set_type": "expansion",
        "games": ["paper"],
        "collector_number": "1",
        "released_at": updated,
        "finishes": ["nonfoil"],
        "image_uris": {"normal": f"https://example.test/{print_id}.jpg"},
        "oracle_text": "Search your library for a land card.",
        "legalities": {"commander": "legal"},
        "prices": {"usd": "1.25"},
        "color_identity": ["W", "U"],
        "type_line": "Land Creature - Test",
        "mana_cost": "{2}{U}",
        "cmc": 3,
        "power": "*",
        "toughness": "4",
        "purchase_uris": {"unused": "https://unused.example.test"},
    }


def test_store_round_trips_consumed_fields_without_raw_payload(tmp_path: Path) -> None:
    path = store.store_path(tmp_path, "fixture")
    store.build_from_cards(
        path,
        [
            _printing("old", set_code="set1", updated="2020-01-01"),
            _printing("new", set_code="set2", updated="2024-01-01"),
        ],
    )
    database = store.CardStore(path)
    matches = database.by_name(["Fetch Land"])["fetch land"]
    assert [match.card.print_id for match in matches] == ["new", "old"]
    card = database.printings_of("oracle-fetchland")[0]
    assert card.print_id == "new"
    assert card.oracle_text == "Search your library for a land card."
    assert card.commander_legal
    assert card.prices["usd"] == "1.25"
    assert card.prices["eur"] is None
    assert card.color_identity == frozenset({"W", "U"})
    assert card.type_line == "Land Creature - Test"
    assert card.mana_value == 3
    assert card.mana_cost == "{2}{U}"
    assert card.power == "*"
    assert card.toughness == "4"
    assert card.faces[0].image_url == "https://example.test/new.jpg"
    old_card = database.by_print_id("old")
    assert old_card is not None
    assert old_card.set_code == "set1"
    columns = {row[1] for row in database._connection.execute("PRAGMA table_info(prints)")}
    assert "payload_json" not in columns
    assert "purchase_uris" not in columns
    assert not hasattr(card, "payload")
    database.close()
    assert store.validate_store(path)
    readonly = store.CardStore(path)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        readonly._connection.execute("DELETE FROM prints")
    readonly.close()


def test_api_and_database_share_only_consumed_fields(tmp_path: Path) -> None:
    payload = _printing("print", set_code="set", updated="2024-01-01")
    prices = {
        "usd": "1.25",
        "usd_foil": "2.50",
        "usd_etched": "3.75",
        "eur": "1.00",
        "eur_foil": "2.00",
        "tix": "0.05",
    }
    payload["prices"] = {**prices, "unused": "99.99"}
    path = store.store_path(tmp_path, "fields")
    store.build_from_cards(path, [payload])
    database = store.CardStore(path)
    card = database.by_print_id("print")

    assert card == replace(store.card_from_payload(payload), is_default_print=True)
    assert card is not None
    assert card.prices == prices
    database.close()


def test_oracle_tag_index_returns_all_printings_by_oracle_identity(tmp_path: Path) -> None:
    cards = [
        _printing("old", set_code="set1", updated="2020-01-01"),
        _printing("new", set_code="set2", updated="2024-01-01"),
        {"id": "unrelated", "oracle_id": "oracle-other", "name": "Island", "games": ["paper"]},
    ]
    tags = [
        {
            "object": "tag",
            "type": "oracle",
            "slug": "cycle-fetchland",
            "taggings": [
                {"oracle_id": "oracle-fetchland", "weight": "median"},
                {"oracle_id": "oracle-other", "weight": "low"},
                {"oracle_id": "oracle-invalid"},
            ],
        },
        {"object": "tag", "type": "card", "slug": "ignored", "taggings": [{"oracle_id": "oracle-fetchland"}]},
        {"object": "tag", "type": "oracle", "slug": "empty", "taggings": []},
    ]
    path = tmp_path / "with-tags.db"
    store.build_from_cards(path, cards, tags=tags)
    database = store.CardStore(path)

    assert database.has_oracle_tags
    columns = {row[1] for row in database._connection.execute("PRAGMA table_info(oracle_tags)")}
    assert columns == {"tag_slug", "oracle_id"}
    assert {card.print_id for card in database.cards_for_tag("cycle-fetchland")} == {"old", "new", "unrelated"}
    assert [card.print_id for card in database.cards_for_tag("empty")] == []
    assert database.cards_for_tag("otag:cycle-fetchland") == database.cards_for_tag("cycle-fetchland")
    database.close()


def test_tag_printing_coverage_detects_missing_default_print_rows(tmp_path: Path) -> None:
    path = tmp_path / "incomplete-tags.db"
    tags = [
        {
            "object": "tag",
            "type": "oracle",
            "slug": "fetchland",
            "taggings": [
                {"oracle_id": "oracle-fetchland"},
                {"oracle_id": "oracle-missing-default"},
            ],
        }
    ]
    store.build_from_cards(path, [_printing("available", set_code="set", updated="2024-01-01")], tags=tags)
    database = store.CardStore(path)

    assert not database.has_complete_tag_printings("otag:fetchland")
    assert [card.print_id for card in database.cards_for_tag("fetchland")] == ["available"]
    database.close()


def test_parent_tag_collects_taggings_recursively_from_leaf_descendants(tmp_path: Path) -> None:
    path = tmp_path / "hierarchy.db"
    tags = [
        {
            "object": "tag",
            "type": "oracle",
            "id": "parent-id",
            "slug": "cycle-fetchland",
            "parent_ids": [],
            "child_ids": ["child-id"],
            "taggings": [],
        },
        {
            "object": "tag",
            "type": "oracle",
            "id": "child-id",
            "slug": "cycle-zendikar-fetchland",
            "parent_ids": ["parent-id"],
            "child_ids": ["leaf-id"],
            "taggings": [],
        },
        {
            "object": "tag",
            "type": "oracle",
            "id": "leaf-id",
            "slug": "cycle-zen-fetchland",
            "parent_ids": ["child-id"],
            "child_ids": [],
            "taggings": [{"oracle_id": "oracle-fetchland", "weight": "strong"}],
        },
    ]
    store.build_from_cards(
        path,
        [_printing("leaf-print", set_code="set", updated="2024-01-01")],
        tags=tags,
    )
    database = store.CardStore(path)

    assert [card.print_id for card in database.cards_for_tag("otag:cycle-fetchland")] == ["leaf-print"]
    assert database.has_complete_tag_printings("cycle-fetchland")
    database.close()


@pytest.mark.parametrize("version", [5, 6, 7])
def test_old_generation_schema_is_rejected_and_tags_are_optional(tmp_path: Path, version: int) -> None:
    path = tmp_path / f"cards-old-v{version}.db"
    path.write_bytes(b"old schema")
    assert not store.validate_store(path)

    current = store.store_path(tmp_path, "no-tags")
    store.build_from_cards(current, [_printing("print", set_code="set", updated="2024-01-01")])
    database = store.CardStore(current)
    assert not database.has_oracle_tags
    with pytest.raises(LookupError, match="not available"):
        database.cards_for_tag("cycle-fetchland")
    database.close()


def test_bulk_builder_streams_tag_file_and_marks_provenance(tmp_path: Path) -> None:
    oracle = tmp_path / "oracle.jsonl.gz"
    default = tmp_path / "default.jsonl.gz"
    tags = tmp_path / "tags.jsonl.gz"
    payload = _printing("print", set_code="set", updated="2024-01-01")
    for path, rows in (
        (oracle, [{"id": "print", "oracle_id": "oracle-fetchland"}]),
        (default, [payload]),
        (tags, [{"object": "tag", "type": "oracle", "slug": "fetch", "taggings": [{"oracle_id": "oracle-fetchland"}]}]),
    ):
        with gzip.open(path, "wt", encoding="utf-8") as output:
            for row in rows:
                output.write(json.dumps(row) + "\n")
    destination = tmp_path / "built.db"
    store.build(destination, oracle, default, tags_path=tags, bulk_version="bulk-version", built_at="2026-10-15")
    database = store.CardStore(destination)
    assert database.bulk_version == "bulk-version"
    assert database.built_at == "2026-10-15"
    assert database.has_oracle_tags
    assert database.cards_for_tag("fetch")[0].prices["usd"] == "1.25"
    database.close()


def test_tag_query_rejects_non_oracle_data() -> None:
    assert store.normalize_name("Fire/Ice") == "fire // ice"
