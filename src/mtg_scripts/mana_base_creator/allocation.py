"""Budget allocation, basic-land fill, and terminal rendering."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ManaBaseLimits


def add_specific_lands(config: ManaBaseLimits, lands: list[str], total_price: float, cards: dict[str, float]) -> float:
    for card, price in cards.items():
        if total_price + price <= config.budget and len(lands) < config.total_lands - config.min_basics:
            lands.append(card)
            total_price += price
            print(f"Adding specific land '{card}' with price {price:.2f}. Total price: {total_price:.2f}.")
        elif total_price + price > config.budget:
            print(f"Skipping specific land '{card}' because it exceeds the remaining budget.")
        elif len(lands) >= config.total_lands - config.min_basics:
            print(f"Skipping specific land '{card}' because it would exceed the land count.")
    return total_price


def add_land_groups(
    config: ManaBaseLimits, lands: list[str], total_price: float, groups: dict[str, dict[str, float]]
) -> float:
    for group, cards in groups.items():
        group_total_price = sum(cards.values())
        within_budget = total_price + group_total_price <= config.budget
        within_count = len(lands) + len(cards) <= config.total_lands - config.min_basics
        if within_budget and within_count:
            lands.extend(cards.keys())
            total_price += group_total_price
            print(f"Adding {len(cards)} lands in group '{group}' with price {group_total_price:.2f}.")
        elif total_price + group_total_price > config.budget:
            print(f"Skipping group '{group}' because it exceeds the remaining budget.")
        elif len(lands) + len(cards) > config.total_lands - config.min_basics:
            print(f"Skipping group '{group}' because it would exceed the land count.")
    return total_price


def fill_basic_lands(config: ManaBaseLimits, lands: list[str]) -> None:
    basic_land_names = {"w": "Plains", "u": "Island", "b": "Swamp", "r": "Mountain", "g": "Forest", "c": "Wastes"}
    while len(lands) < config.total_lands:
        for color in config.colors:
            lands.append(basic_land_names[color])
            if len(lands) >= config.total_lands:
                return


def render_mana_base(lands: list[str], total_price: float) -> None:
    print(f"Final Mana Base ({len(lands)} lands, total price: {total_price:.2f}):")
    for land, count in Counter(sorted(lands)).items():
        print(f"{count} {land}")
