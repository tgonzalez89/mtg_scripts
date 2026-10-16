from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from mtg_scripts.mana_base_creator import (
    candidate_acquisition,
    land_filter,
    mana_base_creator,
    mana_base_recipe,
)
from mtg_scripts.mana_base_creator.models import CardFilterConfig
from mtg_scripts.services.scryfall.store import card_from_payload

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mtg_scripts.mana_base_creator.models import CreatorConfig
    from mtg_scripts.services.scryfall import ScryfallService
    from mtg_scripts.services.scryfall.models import ScryfallCard


def _card(payload: Mapping[str, Any]) -> ScryfallCard:
    return card_from_payload({"id": payload.get("name", "test"), **payload})


class _NameMatch:
    def __init__(self, card: ScryfallCard) -> None:
        self.card = card


class _SearchResult:
    def __init__(self, payloads: list[Mapping[str, Any]]) -> None:
        self.cards = tuple(_card(payload) for payload in payloads)


class _SearchService:
    def __init__(self, responses: dict[str, list[Mapping[str, Any]]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, bool]] = []
        self.tags: dict[str, list[ScryfallCard]] = {}
        self.names: dict[str, list[ScryfallCard]] = {}

    def cards_for_tag(self, slug: str) -> list[ScryfallCard] | None:
        return self.tags.get(slug)

    def resolve_names(self, names: Sequence[str], *, include_flavor: bool = True) -> dict[str, list[_NameMatch]]:
        return {name.casefold(): [_NameMatch(card) for card in self.names.get(name.casefold(), [])] for name in names}

    def search(self, query: str, *, price_sensitive: bool = False) -> _SearchResult:
        self.calls.append((query, price_sensitive))
        return _SearchResult(self.responses.get(query, []))


def test_disabled_group_excludes_matching_cards_from_other_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    enabled_group = "otag:cycle-mh3-mdfc-dual-land"
    disabled_query = 'is:mdfc t:land -produces:m o:"This land enters tapped."'
    tapped_card = _card(
        {
            "name": "Tapped MDFC",
            "oracle_text": "",
            "prices": {"eur": "1"},
        }
    )
    other_card = _card(
        {
            "name": "Other Candidate",
            "oracle_text": "",
            "prices": {"eur": "1"},
        }
    )

    def populate_groups(groups: list[str], price_source: str, service: object = None) -> dict[str, list[ScryfallCard]]:
        if groups == [enabled_group]:
            return {enabled_group: [tapped_card, other_card]}
        return {disabled_query: [tapped_card]}

    monkeypatch.setattr(candidate_acquisition, "populate_cards_from_groups", populate_groups)
    monkeypatch.setattr(
        candidate_acquisition, "populate_cards_from_names", lambda names, price_source, service=None: []
    )
    args = Namespace(
        enable_groups=[enabled_group],
        disable_groups=[disabled_query],
        enable_specific_lands=[],
        disable_specific_lands=[],
        price_source="eur",
    )
    config = CardFilterConfig(
        colors="ur",
        price_source="eur",
        max_price_group_average=3,
        max_price_specific_lands=3,
        allow_off_color_lands=False,
    )

    groups, specific_lands = candidate_acquisition.filter_candidates(args, config)

    assert groups == {enabled_group: {"Other Candidate": 1.0}}
    assert specific_lands == {}


@pytest.mark.parametrize(
    "legacy_option",
    [
        "--total_lands",
        "--min_basics",
        "--price_source",
        "--max_price_group_average",
        "--max_price_specific_lands",
        "--enable_groups",
        "--disable_groups",
        "--enable_specific_lands",
        "--disable_specific_lands",
        "--allow_off_color_lands",
    ],
)
def test_underscore_option_spellings_are_rejected(legacy_option: str) -> None:
    with pytest.raises(SystemExit) as raised:
        mana_base_creator.parse_arguments(["--colors", "wg", legacy_option])
    assert raised.value.code == 2


def test_invalid_colors_use_parser_status() -> None:
    with pytest.raises(SystemExit) as raised:
        mana_base_creator.main(["--colors", "ww"])
    assert raised.value.code == 2


def test_recipe_preserves_overrides_and_creator_status(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[float] = []

    def creator(config: CreatorConfig) -> int:
        received.append(config.budget)
        return 9

    monkeypatch.setattr(mana_base_recipe, "run_creator", creator)
    assert mana_base_recipe.main(["low", "all", "wg", "40", "5", "eur", "--budget", "7"]) == 9
    assert received == [7]


def test_group_queries_keep_oracle_tag_legality_and_price_ordering() -> None:
    query = "game:paper legal:commander order:eur dir:asc otag:cycle-fetchland"
    service = _SearchService({query: []})

    assert candidate_acquisition.populate_cards_from_groups(
        ["otag:cycle-fetchland"], "eur", cast("ScryfallService", service)
    ) == {"otag:cycle-fetchland": []}
    assert service.calls == [(query, True)]


def test_oracle_tag_groups_filter_local_printings_and_pick_cheapest_per_oracle() -> None:
    service = _SearchService({})
    service.tags["otag:cycle-fetchland"] = [
        _card(
            {
                "name": "Fabled Passage",
                "oracle_id": "fetch-1",
                "games": ["paper"],
                "legalities": {"commander": "legal"},
                "prices": {"eur": "8.00"},
            }
        ),
        _card(
            {
                "name": "Fabled Passage",
                "oracle_id": "fetch-1",
                "games": ["paper"],
                "legalities": {"commander": "legal"},
                "prices": {"eur": "3.00"},
            }
        ),
        _card(
            {
                "name": "Digital Fetch",
                "oracle_id": "fetch-2",
                "games": ["arena"],
                "legalities": {"commander": "legal"},
                "prices": {"eur": "0.01"},
            }
        ),
        _card(
            {
                "name": "Banned Fetch",
                "oracle_id": "fetch-3",
                "games": ["paper"],
                "legalities": {"commander": "banned"},
                "prices": {"eur": "0.02"},
            }
        ),
    ]

    groups = candidate_acquisition.populate_cards_from_groups(
        ["otag:cycle-fetchland"], "eur", cast("ScryfallService", service)
    )

    assert [card.name for card in groups["otag:cycle-fetchland"]] == ["Fabled Passage"]
    assert groups["otag:cycle-fetchland"][0].prices["eur"] == "3.00"
    assert service.calls == []


@pytest.mark.parametrize(
    "local_cards",
    [
        [],
        [
            _card(
                {
                    "name": "Fetch Without Price",
                    "oracle_id": "fetch-missing-price",
                    "games": ["paper"],
                    "legalities": {"commander": "legal"},
                    "prices": {"usd": None},
                }
            )
        ],
    ],
)
def test_empty_or_incomplete_local_tag_data_falls_back_to_api(
    local_cards: list[ScryfallCard],
) -> None:
    group = "otag:cycle-fetchland"
    query = f"game:paper legal:commander order:usd dir:asc {group}"
    api_card = {"name": "API Fetchland", "oracle_text": "", "prices": {"usd": "2.00"}}
    service = _SearchService({query: [api_card]})
    service.tags[group] = local_cards

    groups = candidate_acquisition.populate_cards_from_groups([group], "usd", cast("ScryfallService", service))

    assert [card.name for card in groups[group]] == ["API Fetchland"]
    assert service.calls == [(query, True)]


def test_exact_name_selection_uses_first_price_ordered_matching_printing() -> None:
    query = 'game:paper legal:commander order:eur dir:asc !"mana confluence"'
    cheap = {"name": "Mana Confluence", "oracle_text": "", "prices": {"eur": "4.00"}}
    expensive = {"name": "Mana Confluence", "oracle_text": "", "prices": {"eur": "18.00"}}
    service = _SearchService({query: [cheap, expensive]})

    cards = candidate_acquisition.populate_cards_from_names(
        ["mana confluence"], "eur", cast("ScryfallService", service)
    )

    assert cards == [_card(cheap)]
    assert service.calls == [(query, True)]


def test_specific_names_use_batched_local_name_lookup_before_api() -> None:
    service = _SearchService({})
    service.names["command tower"] = [
        _card(
            {
                "name": "Command Tower",
                "oracle_id": "tower-1",
                "games": ["paper"],
                "legalities": {"commander": "legal"},
                "prices": {"usd": "3.00"},
            }
        ),
        _card(
            {
                "name": "Command Tower",
                "oracle_id": "tower-1",
                "games": ["paper"],
                "legalities": {"commander": "legal"},
                "prices": {"usd": "1.00"},
            }
        ),
    ]

    cards = candidate_acquisition.populate_cards_from_names(["command tower"], "usd", cast("ScryfallService", service))

    assert [card.prices["usd"] for card in cards] == ["1.00"]
    assert service.calls == []


def test_unclassified_fetchland_still_uses_oracle_tag_membership_query() -> None:
    query = 'game:paper legal:commander order:usd dir:asc otag:fetchland !"Fabled Passage"'
    fetchland = _card(
        {
            "name": "Fabled Passage",
            "oracle_text": "Search your library for a Plains or Island card.",
            "prices": {"usd": "4.00"},
        }
    )
    service = _SearchService({query: [{"name": fetchland.name}]})

    assert land_filter.should_remove_fetchland(
        fetchland,
        None,
        "w",
        allow_off_color_lands=False,
        service=cast("ScryfallService", service),
    )
    assert service.calls == [(query, True)]


def test_stale_price_use_requires_explicit_option() -> None:
    assert not mana_base_creator.parse_arguments(["--colors", "w"]).allow_stale_data
    assert mana_base_creator.parse_arguments(["--colors", "w", "--allow-stale-data"]).allow_stale_data
