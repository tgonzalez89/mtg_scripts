from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self, cast

from mtg_scripts.other_scripts import vanilla
from mtg_scripts.services.scryfall.store import card_from_payload

if TYPE_CHECKING:
    from collections.abc import Mapping

    import pytest

    from mtg_scripts.services.scryfall import ScryfallService
    from mtg_scripts.services.scryfall.models import ScryfallCard


def _card(payload: dict[str, Any]) -> ScryfallCard:
    return card_from_payload({"id": payload.get("name", "test"), **payload})


class _SearchResult:
    def __init__(self, cards: tuple[ScryfallCard, ...]) -> None:
        self.cards = cards


class _FakeService:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, Mapping[str, str | None]]] = []
        self.closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def search(
        self,
        query: str,
        *,
        order: str | None = None,
        direction: str | None = None,
    ) -> _SearchResult:
        self.calls.append((query, {"order": order, "direction": direction}))
        return _SearchResult((_card(self.payload),))


def test_fetch_uses_shared_service_preserving_query_order_and_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload: dict[str, Any] = {
        "name": "Vanilla Giant",
        "type_line": "Creature - Giant",
        "power": "4",
        "toughness": "4",
        "mana_value": 5,
        "mana_cost": "{4}{G}",
        "prices": {"usd": "0.25"},
    }
    service = _FakeService(payload)
    monkeypatch.setattr(vanilla, "ScryfallService", lambda: service, raising=False)

    assert vanilla.fetch_scryfall_cards('name:"Vanilla Giant"') == [_card(payload)]
    assert service.calls == [('name:"Vanilla Giant"', {"order": "cmc", "direction": "asc"})]
    assert service.closed


def test_ranking_preserves_fallback_zero_mana_unknown_stats_and_formatting() -> None:
    cards = [
        _card({"name": "Fallback", "cmc": 2, "power": "4", "toughness": "3", "mana_cost": "{1}{G}"}),
        _card({"name": "Fast", "mana_value": 2, "power": "6", "toughness": "2", "mana_cost": "{2}{G}"}),
        _card({"name": "Zero", "mana_value": 0, "power": "3", "toughness": "3"}),
        _card({"name": "Unknown", "mana_value": 3, "power": "*", "toughness": "5"}),
    ]

    ranked = vanilla.rank_cards(cards)

    assert [card["name"] for card in ranked] == ["Fast", "Fallback", "Zero"]
    assert ranked[0]["efficiency"] == 3.0
    assert vanilla.format_card_line(ranked[0]) == "Fast | 2 | {2}{G} | 6/2 | 3.0"
    assert [card["name"] for card in vanilla.rank_cards(cards, min_mana_value=1, min_power=4)] == [
        "Fast",
        "Fallback",
    ]


def test_fetch_does_not_close_a_borrowed_service() -> None:
    payload: dict[str, Any] = {"name": "Borrowed"}
    service = _FakeService(payload)

    assert vanilla.fetch_scryfall_cards("name:borrowed", cast("ScryfallService", service)) == [_card(payload)]
    assert not service.closed
