from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mtg_scripts.print_picker.models import PrintQuery, display_label
from mtg_scripts.print_picker.riftcodex_backend import RiftCodexBackend, _matches_identity

if TYPE_CHECKING:
    from pathlib import Path


def _item(**overrides: object) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "abc123",
        "riftbound_id": "ogs-017-024",
        "name": "Annie - Dark Child (Starter)",
        "collector_number": 17,
        "set": {"set_id": "OGS", "label": "Proving Grounds"},
        "metadata": {"clean_name": "Annie - Dark Child"},
        "media": {"image_url": "https://example.test/annie.png"},
    }
    item.update(overrides)
    return item


def _backend(tmp_path: Path) -> RiftCodexBackend:
    backend = RiftCodexBackend(cache_dir=tmp_path)
    # Release dates come from a per-set endpoint; stub it so no request is made.
    backend._set_release_dates["ogs"] = "2025-10-31T00:00:00"
    backend._set_release_dates["ogn"] = "2025-10-31T00:00:00"
    return backend


def test_parse_line_splits_the_printing_code() -> None:
    entry = RiftCodexBackend.parse_line("3 Traveling Merchant (OGN-185)")
    assert entry.quantity == 3
    assert entry.name == "Traveling Merchant"
    assert entry.query == PrintQuery(set_code="ogn", collector_number="185")


def test_parse_line_without_a_printing_code() -> None:
    entry = RiftCodexBackend.parse_line("2 Tibbers")
    assert entry.quantity == 2
    assert entry.name == "Tibbers"
    assert not entry.query


def test_collector_number_keeps_the_padded_decklist_form(tmp_path: Path) -> None:
    """The API reports 17, but decklists and `riftbound_id` both say 017."""
    card = _backend(tmp_path)._to_print(_item())
    assert card.collector_number == "017"


def test_padded_printing_code_matches_its_card(tmp_path: Path) -> None:
    card = _backend(tmp_path)._to_print(_item())
    query = RiftCodexBackend.parse_line("1 Annie - Dark Child - Starter (OGS-017)").query
    assert _matches_identity(card, query)


def test_a_different_set_does_not_match(tmp_path: Path) -> None:
    card = _backend(tmp_path)._to_print(_item(riftbound_id="opp-017-024", set={"set_id": "OPP", "label": "Proving"}))
    query = RiftCodexBackend.parse_line("1 Annie - Dark Child - Starter (OGS-017)").query
    assert not _matches_identity(card, query)


def test_mapped_fields(tmp_path: Path) -> None:
    card = _backend(tmp_path)._to_print(_item())
    assert card.backend == "riftcodex"
    assert card.print_id == "abc123"
    assert card.set_code == "OGS"
    assert card.set_name == "Proving Grounds"
    assert card.released_on == "2025-10-31T00:00:00"
    # The printing-independent clean name groups a card's printings together.
    assert card.card_key == "Annie - Dark Child"
    assert card.image_urls() == ("https://example.test/annie.png",)
    assert display_label(card) == "Proving Grounds (OGS) #017"


def test_unparseable_riftbound_id_falls_back_to_the_raw_number(tmp_path: Path) -> None:
    card = _backend(tmp_path)._to_print(_item(riftbound_id="", collector_number=17))
    assert card.collector_number == "17"


def test_close_releases_cached_release_dates(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    assert backend._set_release_dates
    backend.close()
    assert backend._set_release_dates == {}


def test_export_uses_the_printing_code_import_syntax(tmp_path: Path) -> None:
    card = _backend(tmp_path)._to_print(_item())
    entry = RiftCodexBackend.parse_line("1 Annie - Dark Child - Starter (OGS-017)")
    assert RiftCodexBackend.export_card_text(card, entry) == "Annie - Dark Child (Starter) (OGS-017)"


def test_exported_text_reimports_to_the_same_printing(tmp_path: Path) -> None:
    """The exported line must parse back to the same set and collector number."""
    backend = _backend(tmp_path)
    for line, item in (
        ("1 Annie - Dark Child - Starter (OGS-017)", _item()),
        (
            "3 Traveling Merchant (OGN-185)",
            _item(
                riftbound_id="ogn-185-298",
                name="Traveling Merchant",
                collector_number=185,
                set={"set_id": "OGN", "label": "Origins"},
            ),
        ),
    ):
        card = backend._to_print(item)
        entry = RiftCodexBackend.parse_line(line)
        exported = RiftCodexBackend.export_card_text(card, entry)
        reparsed = RiftCodexBackend.parse_line(f"1 {exported}")
        assert reparsed.query == entry.query, f"{line} -> {exported!r}"
        assert _matches_identity(card, reparsed.query), exported


def test_export_falls_back_to_the_name_without_a_printing_code(tmp_path: Path) -> None:
    card = _backend(tmp_path)._to_print(_item(riftbound_id="", collector_number=None, set={}))
    entry = RiftCodexBackend.parse_line("2 Annie - Dark Child - Starter")
    assert RiftCodexBackend.export_card_text(card, entry) == "Annie - Dark Child (Starter)"
