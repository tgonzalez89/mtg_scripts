"""Mana-base Scryfall acquisition through the shared provider service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtg_scripts.services.scryfall import ScryfallService

SCRYFALL_BASE_QUERY = "game:paper legal:commander order:{price_source} dir:asc"

if TYPE_CHECKING:
    from mtg_scripts.services.scryfall.models import ScryfallCard


def query_scryfall(query: str, service: ScryfallService | None = None) -> list[ScryfallCard]:
    """Search the full Scryfall query language, including price/order semantics."""
    if service is None:
        with ScryfallService() as owned_service:
            return query_scryfall(query, owned_service)
    result = service.search(query, price_sensitive=True)
    return list(result.cards)
