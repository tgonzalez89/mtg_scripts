"""EDHREC-specific client adapter used by the base-deck workflow."""

from __future__ import annotations

from collections.abc import Callable
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
            return {"commander": card_name, "decklist": cast("list[str]", data.get("deck") or [])}

    return cast("EDHRecClient", MyEDHRec())
