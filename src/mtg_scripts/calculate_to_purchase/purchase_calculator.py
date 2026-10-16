"""Pure inventory and deck-requirement calculations for purchase reports."""

from __future__ import annotations

from dataclasses import dataclass

type CardCounts = dict[str, int]


@dataclass(frozen=True, slots=True)
class PurchaseInputs:
    cards_in_decks: CardCounts
    considering_cards: CardCounts
    available: CardCounts
    purchased: CardCounts
    owned: CardCounts
    buy_considering: bool


@dataclass(frozen=True, slots=True)
class PurchaseCalculation:
    need: CardCounts
    need_decks: CardCounts
    need_considering: CardCounts
    to_purchase: CardCounts
    to_purchase_decks: CardCounts
    to_purchase_considering: CardCounts
    avoided: CardCounts
    avoided_owned: CardCounts
    avoided_purchased: CardCounts


def combine_inventory(owned: CardCounts, purchased: CardCounts) -> CardCounts:
    available = owned.copy()
    for name, amount in purchased.items():
        available[name] = available.get(name, 0) + amount
    return available


def merge_deck_variants(decks: list[CardCounts]) -> CardCounts:
    """Use the largest quantity found across mutually exclusive deck variants."""
    merged: CardCounts = {}
    for deck in decks:
        for name, amount in deck.items():
            merged[name] = max(merged.get(name, 0), amount)
    return merged


def add_wanted_deck(
    cards_in_decks: CardCounts,
    considering_cards: CardCounts,
    main_deck: CardCounts,
    maybeboard: CardCounts,
    excluded: set[str],
) -> tuple[CardCounts, CardCounts]:
    cards = cards_in_decks.copy()
    considering = considering_cards.copy()
    for name, amount in main_deck.items():
        if name not in excluded:
            cards[name] = cards.get(name, 0) + amount
    for name, amount in maybeboard.items():
        if name not in excluded:
            considering[name] = considering.get(name, 0) + amount
    return cards, considering


def allocate_have_deck(available: CardCounts, main_deck: CardCounts) -> CardCounts:
    """Return inventory remaining after assigning cards to already-owned decks."""
    remaining = available.copy()
    for name, amount in main_deck.items():
        if name not in remaining:
            continue
        if remaining[name] > amount:
            remaining[name] -= amount
        else:
            remaining.pop(name)
    return remaining


def calculate_purchase(
    inputs: PurchaseInputs,
) -> PurchaseCalculation:
    need, need_considering = _build_needs(
        inputs.cards_in_decks, inputs.considering_cards, buy_considering=inputs.buy_considering
    )
    to_purchase, avoided, avoided_owned, avoided_purchased = _account_requirements(
        need, inputs.available, inputs.purchased, inputs.owned
    )

    return PurchaseCalculation(
        need=need,
        need_decks=inputs.cards_in_decks.copy(),
        need_considering=need_considering,
        to_purchase=to_purchase,
        to_purchase_decks=_remaining_requirements(inputs.cards_in_decks, inputs.available),
        to_purchase_considering=_remaining_requirements(need_considering, inputs.available),
        avoided=avoided,
        avoided_owned=avoided_owned,
        avoided_purchased=avoided_purchased,
    )


def _build_needs(
    cards_in_decks: CardCounts, considering_cards: CardCounts, *, buy_considering: bool
) -> tuple[CardCounts, CardCounts]:
    need = cards_in_decks.copy()
    need_considering: CardCounts = {}
    if buy_considering:
        for name in considering_cards:
            if name not in need:
                need[name] = 1
                need_considering[name] = 1
    return need, need_considering


def _account_requirements(
    need: CardCounts, available: CardCounts, purchased: CardCounts, owned: CardCounts
) -> tuple[CardCounts, CardCounts, CardCounts, CardCounts]:
    to_purchase: CardCounts = {}
    avoided: CardCounts = {}
    avoided_owned: CardCounts = {}
    avoided_purchased: CardCounts = {}
    for name, amount in need.items():
        if name not in available:
            to_purchase[name] = amount
            continue
        avoided[name] = min(amount, available[name])
        if amount > available[name]:
            to_purchase[name] = amount - available[name]
            if name in purchased:
                avoided_purchased[name] = purchased[name]
            if name in owned:
                avoided_owned[name] = owned[name]
        else:
            if name in purchased:
                avoided_purchased[name] = min(amount, purchased[name])
            if name in owned and amount - avoided_purchased.get(name, 0) > 0:
                avoided_owned[name] = amount - avoided_purchased.get(name, 0)
    return to_purchase, avoided, avoided_owned, avoided_purchased


def _remaining_requirements(need: CardCounts, available: CardCounts) -> CardCounts:
    return {
        name: amount if name not in available else amount - available[name]
        for name, amount in need.items()
        if name not in available or available[name] < amount
    }
