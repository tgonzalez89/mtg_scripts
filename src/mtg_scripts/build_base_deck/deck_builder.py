"""Pure card-selection, occurrence, and output helpers for base-deck generation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

type CardData = dict[str, Any]

if TYPE_CHECKING:
    from pathlib import Path


def collect_eligible_cards(
    cardlists: list[dict[str, Any]], *, lift_threshold: float, inclusion_threshold: float
) -> dict[str, CardData]:
    cards: dict[str, CardData] = {}
    for card_list in cardlists:
        for card in card_list["cardviews"]:
            lift = card.get("lift")
            if (isinstance(lift, (int, float)) and lift >= lift_threshold) or (
                card["num_decks"] / card["potential_decks"] >= inclusion_threshold
            ):
                cards[card["name"]] = card
    return cards


def filter_candidate_prices(
    candidates: dict[str, CardData], card_data: dict[str, Any], *, vendor: str, price_threshold: float
) -> dict[str, CardData]:
    for card in card_data["cards"].values():
        price = card["prices"][vendor]["price"]
        if price <= price_threshold:
            candidates[card["name"]]["price"] = price
        else:
            candidates.pop(card["name"])
    return candidates


def filter_average_deck_prices(
    decklist: list[str], card_data: dict[str, Any], *, vendor: str, price_threshold: float
) -> list[str]:
    filtered = decklist.copy()
    for card in card_data["cards"].values():
        if card["prices"][vendor]["price"] > price_threshold:
            filtered.remove(card["name"])
    return filtered


def count_card_occurrences(*card_groups: Iterable[str] | Mapping[str, object]) -> Counter[str]:
    occurrences: Counter[str] = Counter()
    for group in card_groups:
        occurrences.update(group.keys() if isinstance(group, Mapping) else group)
    return occurrences


def classify_cards(occurrences: Counter[str], *, theme_count: int, commander_count: int) -> tuple[list[str], list[str]]:
    required = theme_count * commander_count
    main_deck = [name for name, count in occurrences.items() if count >= 3 * required]
    considering = [name for name, count in occurrences.items() if count <= 2 * required]
    return main_deck, considering


def write_card_list(path: Path, main_deck: list[str], considering: list[str]) -> None:
    with path.open("w") as output:
        output.write("# MAIN DECK\n")
        output.writelines(name + "\n" for name in sorted(main_deck))
        output.write("\n# CONSIDERING\n")
        output.writelines(name + "\n" for name in sorted(considering))
