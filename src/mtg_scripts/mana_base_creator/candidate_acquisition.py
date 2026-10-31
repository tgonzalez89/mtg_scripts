"""Acquire and reconcile enabled/disabled mana-base land candidates."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from mtg_scripts.services.scryfall import ScryfallService

from .land_filter import process_cards
from .scryfall import SCRYFALL_BASE_QUERY, query_scryfall

if TYPE_CHECKING:
    import argparse
    from collections.abc import Sequence

    from mtg_scripts.services.scryfall.models import ScryfallCard

    from .models import CardFilterConfig, CreatorConfig


def populate_cards_from_groups(
    groups: Sequence[str], price_source: str, service: ScryfallService | None = None
) -> dict[str, list[ScryfallCard]]:
    if service is None:
        with ScryfallService() as owned_service:
            return populate_cards_from_groups(groups, price_source, owned_service)

    return {
        group: query_scryfall(f"{SCRYFALL_BASE_QUERY.format(price_source=price_source)} {group}", service)
        for group in groups
    }


def populate_cards_from_names(
    names: Sequence[str], price_source: str, service: ScryfallService | None = None
) -> list[ScryfallCard]:
    if service is None:
        with ScryfallService() as owned_service:
            return populate_cards_from_names(names, price_source, owned_service)

    cards: list[ScryfallCard] = []
    for name in names:
        query = f'{SCRYFALL_BASE_QUERY.format(price_source=price_source)} !"{name}"'
        data = query_scryfall(query, service)
        with suppress(StopIteration):
            cards.append(next(card for card in data if card.name.casefold() == name.casefold()))
    return cards


def filter_candidates(
    args: argparse.Namespace | CreatorConfig, config: CardFilterConfig, service: ScryfallService | None = None
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    enabled_groups_cards = populate_cards_from_groups(args.enable_groups, args.price_source, service)
    disabled_groups_cards = populate_cards_from_groups(args.disable_groups, args.price_source, service)
    disabled_group_names = {card.name.casefold() for cards in disabled_groups_cards.values() for card in cards}
    enabled_specific = populate_cards_from_names(args.enable_specific_lands, args.price_source, service)
    disabled_specific = populate_cards_from_names(args.disable_specific_lands, args.price_source, service)

    enabled_groups = {
        group: process_cards(cards, config, group=group, service=service)
        for group, cards in enabled_groups_cards.items()
    }
    enabled_specific_cards = process_cards(enabled_specific, config, group="", service=service)
    disabled_specific_cards = process_cards(disabled_specific, config, group="", service=service)

    groups = {
        group: {name: price for name, price in cards.items() if name.casefold() not in disabled_group_names}
        for group, cards in enabled_groups.items()
    }
    groups = {group: cards for group, cards in groups.items() if cards}
    specific = {name: price for name, price in enabled_specific_cards.items() if name not in disabled_specific_cards}
    return groups, specific
