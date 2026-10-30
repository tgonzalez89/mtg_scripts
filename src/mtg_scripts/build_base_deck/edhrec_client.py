"""EDHREC-specific client adapter used by the base-deck workflow."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final, Protocol, TypedDict, cast, override

type CacheDecorator = Callable[[Callable[..., Any]], Callable[..., Any]]

EDHREC_PAGES_URL: Final[str] = "https://json.edhrec.com/pages"
CARD_LIST_BATCH_SIZE: Final[int] = 300


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
        def _get_page_data(
            self, endpoint: str, card_name: str, budget: str | None, theme: str | None
        ) -> dict[str, Any]:
            commander_name = card_name.split("//", maxsplit=1)[0].strip()
            path = [endpoint, self.format_card_name(commander_name)]
            if bool(theme):
                path.append(theme)
            if bool(budget):
                path.append(budget)
            return self._get(f"{EDHREC_PAGES_URL}/{'/'.join(path)}.json")

        @override
        def get_card_list(self, card_list: list[str]) -> dict[str, Any]:
            cards: dict[str, Any] = {}
            for start in range(0, len(card_list), CARD_LIST_BATCH_SIZE):
                response = super().get_card_list(card_list[start : start + CARD_LIST_BATCH_SIZE])
                batch_cards = response.get("cards")
                if not isinstance(batch_cards, dict):
                    errors = response.get("errors")
                    if errors:
                        message = "; ".join(str(error) for error in errors)
                        msg = f"EDHREC card lookup failed: {message}"
                        raise RuntimeError(msg)
                    msg = "EDHREC card lookup response did not contain a cards mapping."
                    raise TypeError(msg)
                cards.update(batch_cards)
            return {"cards": cards}

        @commander_cache
        @override
        def get_commander_data(
            self, card_name: str, budget: str | None = None, theme: str | None = None
        ) -> dict[str, Any]:
            return self._get_page_data("commanders", card_name, budget, theme)

        @average_deck_cache
        @override
        def get_commanders_average_deck(
            self, card_name: str, budget: str | None = None, theme: str | None = None
        ) -> AverageDeckResult:
            data = self._get_page_data("average-decks", card_name, budget, theme)
            return {"commander": card_name, "decklist": _normalize_average_decklist(data.get("deck"))}

    return cast("EDHRecClient", MyEDHRec())
