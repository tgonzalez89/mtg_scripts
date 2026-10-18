"""EDHREC-specific client adapter used by the base-deck workflow."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, TypedDict, cast, override

type CacheDecorator = Callable[[Callable[..., Any]], Callable[..., Any]]


class AverageDeckResult(TypedDict):
    commander: str
    decklist: list[str]


class EDHRecClient(Protocol):
    def get_commander_data(
        self, card_name: str, budget: str | None = None, theme: str | None = None
    ) -> dict[str, Any]: ...

    def get_card_list(self, card_names: list[str]) -> dict[str, Any]: ...

    def get_commanders_average_deck(
        self, card_name: str, budget: str | None = None, theme: str | None = None
    ) -> AverageDeckResult: ...


def _card_name(entry: object) -> str | None:
    if isinstance(entry, str):
        quantity, separator, name = entry.partition(" ")
        return name if separator and quantity.isdecimal() else entry
    if isinstance(entry, (list, tuple)) and entry and isinstance(entry[0], str):
        return entry[0]
    return None


def _normalize_average_decklist(deck: object) -> list[str]:
    if isinstance(deck, list):
        return [name for entry in deck if (name := _card_name(entry)) is not None]
    if not isinstance(deck, Mapping):
        return []

    names: list[str] = []
    card_categories = deck.get("cards", {})
    if isinstance(card_categories, Mapping):
        for entries in card_categories.values():
            if isinstance(entries, list):
                names.extend(name for entry in entries if (name := _card_name(entry)) is not None)

    commander = deck.get("commander") or deck.get("commander_v2", [])
    commander_entries = commander if isinstance(commander, list) else [commander]
    names.extend(name for entry in commander_entries if (name := _card_name(entry)) is not None)
    return names


def create_edhrec_client() -> EDHRecClient:
    """Create the budget/theme-aware EDHREC client without importing it at module load."""
    import pyedhrec  # noqa: PLC0415
    import pyedhrec.caching  # noqa: PLC0415

    commander_cache = cast("CacheDecorator", pyedhrec.caching.commander_cache)
    average_deck_cache = cast("CacheDecorator", pyedhrec.caching.average_deck_cache)

    class MyEDHRec(pyedhrec.EDHRec):
        @commander_cache
        @override
        def get_commander_data(
            self, card_name: str, budget: str | None = None, theme: str | None = None
        ) -> dict[str, Any]:
            commander_uri, params = self._build_nextjs_uri(
                "commanders", card_name, theme=cast("str", theme), budget=cast("str", budget)
            )
            response = self._get(commander_uri, query_params=params)
            return self._get_nextjs_data(response)

        @average_deck_cache
        @override
        def get_commanders_average_deck(
            self, card_name: str, budget: str | None = None, theme: str | None = None
        ) -> AverageDeckResult:
            average_deck_uri, params = self._build_nextjs_uri(
                "average-decks", card_name, theme=cast("str", theme), budget=cast("str", budget)
            )
            response = self._get(average_deck_uri, query_params=params)
            data = self._get_nextjs_data(response)
            return {"commander": card_name, "decklist": _normalize_average_decklist(data.get("deck"))}

    return cast("EDHRecClient", MyEDHRec())
