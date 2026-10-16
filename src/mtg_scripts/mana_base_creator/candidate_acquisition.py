"""Acquire and reconcile enabled/disabled mana-base land candidates."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from mtg_scripts.services.scryfall import ScryfallService
from mtg_scripts.services.scryfall.store import normalize_name

from .land_filter import get_price, process_cards
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

    cards_per_group: dict[str, list[ScryfallCard]] = {}
    for group in groups:
        if _is_simple_oracle_tag(group):
            tagged_cards = service.cards_for_tag(group)
            if tagged_cards is not None:
                local_candidates = _cheapest_local_printings(tagged_cards, price_source)
                if local_candidates is not None:
                    cards_per_group[group] = local_candidates
                    continue
        query = f"{SCRYFALL_BASE_QUERY.format(price_source=price_source)} {group}"
        cards_per_group[group] = query_scryfall(query, service)
    return cards_per_group


def populate_cards_from_names(
    names: Sequence[str], price_source: str, service: ScryfallService | None = None
) -> list[ScryfallCard]:
    if service is None:
        with ScryfallService() as owned_service:
            return populate_cards_from_names(names, price_source, owned_service)

    cards: list[ScryfallCard] = []
    local_matches = service.resolve_names(names, include_flavor=False)
    for name in names:
        matching_printings = [
            match.card
            for match in local_matches.get(normalize_name(name), [])
            if match.card.name.casefold() == name.casefold()
        ]
        local_result = _cheapest_local_printings(matching_printings, price_source)
        if local_result is not None and len(local_result) > 0:
            cards.append(local_result[0])
            continue
        query = f'{SCRYFALL_BASE_QUERY.format(price_source=price_source)} !"{name}"'
        data = query_scryfall(query, service)
        with suppress(StopIteration):
            cards.append(next(card for card in data if card.name.casefold() == name.casefold()))
    return cards


def _is_simple_oracle_tag(group: str) -> bool:
    return group.startswith("otag:") and " " not in group


def _cheapest_local_printings(cards: Sequence[ScryfallCard], price_source: str) -> list[ScryfallCard] | None:
    cheapest_by_oracle: dict[str, tuple[float, ScryfallCard]] = {}
    for card in cards:
        if "paper" not in card.games or not card.commander_legal:
            continue
        prices = card.prices
        has_price = prices.get(price_source) is not None or any(
            name.startswith(price_source) and price is not None for name, price in prices.items()
        )
        if not has_price:
            return None
        price = get_price(price_source, card)
        current = cheapest_by_oracle.get(card.oracle_id)
        if current is None or price < current[0]:
            cheapest_by_oracle[card.oracle_id] = (price, card)
    if not cheapest_by_oracle:
        return None
    ordered = sorted(cheapest_by_oracle.values(), key=lambda candidate: candidate[0])
    return [card for _, card in ordered]


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
