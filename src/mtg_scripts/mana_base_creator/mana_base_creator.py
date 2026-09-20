#!/bin/env python3
import argparse
import hashlib
import json
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import requests

SCRYFALL_API_URL = "https://api.scryfall.com/cards/search"
SCRYFALL_HEADERS = {"User-Agent": "MyMTGApp/1.0 (contact@example.com)", "Accept": "application/json"}
SCRYFALL_BASE_QUERY = "game:paper legal:commander order:{price_source} dir:asc"
HTTP_OK = 200


@dataclass(frozen=True)
class CardFilterConfig:
    """Options used when filtering candidate lands."""

    colors: str
    price_source: str
    max_price_group_average: float
    max_price_specific_lands: float
    allow_off_color_lands: bool


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a mana base for a Commander deck in Magic: The Gathering.")

    parser.add_argument("--colors", type=str, required=True, help='Colors of the deck (e.g., "WUBRG")')
    parser.add_argument("--total_lands", type=int, default=40, help="Total number of lands in the deck")
    parser.add_argument("--min_basics", type=int, default=5, help="Minimum number of basic lands")
    parser.add_argument("--budget", type=float, default=500.0, help="Total budget for lands")
    parser.add_argument(
        "--max_price_group_average",
        type=float,
        default=50.0,
        help="Maximum average price for each of the groups of lands specified in --enable_groups",
    )
    parser.add_argument(
        "--max_price_specific_lands",
        type=float,
        default=50.0,
        help="Maximum price for each of the lands specified in --enable_specific_lands",
    )
    parser.add_argument(
        "--price_source", type=str, default="usd", choices=["usd", "eur", "tix"], help="Source for card prices"
    )
    parser.add_argument(
        "--enable_groups",
        type=str,
        nargs="*",
        help="Enable specific groups of lands (Scryfall queries)",
        default=[
            "otag:cycle-fetchland",  # Fetchlands
            "otag:cycle-abu-dual-land",  # Original duals, fetchable
            "otag:tricycle-land",  # Triomes, enter tapped, cycling, fetchable
            "otag:cycle-shockland",  # Require 2 damage, fetchable
            "otag:cycle-dual-surveil-land",  # Enter tapped, surveil 1, fetchable
            "otag:cycle-bondland",  # Require >=2 opponents
            "otag:cycle-triple-tapland",  # Cheap triomes
            "otag:cycle-painland",  # Good painlands
            "otag:cycle-soc-turbulent-land",  # Require opponents to control >=8 lands, fetchable
            "otag:cycle-slowland",  # Require >=2 other lands
            "otag:cycle-fastland",  # Require <=2 other lands
            "otag:cycle-verge",
            "otag:cycle-msh-lair-dual",
            "otag:cycle-tor-tainted-land",  # Tap for {C}, dual if control a swamp
            "otag:cycle-checkland",  # Require one of the two corresponding basic land types
            "otag:cycle-tangoland",  # Require 2 basic lands, fetchable
            "otag:cycle-reveal-land",  # Require to reveal one of the two corresponding basic land types
            "otag:cycle-pathway",  # MDFC dual lands
            "otag:cycle-horizon-land",  # Painland, can be sacrificed to draw a card
            "otag:cycle-hybrid-filterland",  # Hybrid mana filter lands
            "otag:cycle-ody-filterland",  # Signet-style filter lands
            "otag:cycle-bicycle-land",  # Enter tapped, cycling, fetchable
            "otag:cycle-mh3-mdfc-dual-land",  # MDFC dual lands with spells in the front
            "otag:cycle-scry-land",  # Enter tapped, scry 1
            "otag:cycle-mh3-landscape",  # Basic tri fetches, tap for {C}, can be cycled for 3 colored mana
            "otag:cycle-snc-fetchland",  # Basic tri fetches, are sacrificed automatically and gain 1 life
            "otag:cycle-ala-panorama",  # Basic tri fetches, tap for add {C}, cost 1 to fetch
            "otag:cycle-rav-bounceland",  # Bouncelands
            'is:mdfc t:land (t:instant or t:sorcery or t:enchantment or t:creature or t:artifact) o:"may pay 3 life"',
            (
                "is:mdfc t:land (t:instant or t:sorcery or t:enchantment or t:creature or t:artifact) "
                'o:"This land enters tapped."'
            ),
        ],
    )
    parser.add_argument(
        "--disable_groups", type=str, nargs="*", default=[], help="Disable specific groups of lands (Scryfall queries)"
    )
    parser.add_argument(
        "--enable_specific_lands",
        type=str,
        nargs="*",
        help="Enable specific lands (exact names)",
        default=[
            "Command Tower",  # Tap for any color of mana from your commander
            "Exotic Orchard",  # Tap for any color of mana that a land an opponent could produce
            "Fabled Passage",  # Basic fetchland, fetches land enters tapped unless >= 4 lands
            "Prismatic Vista",  # Basic fetchland
            "Reflecting Pool",  # Tap for any color of mana that a land you control could produce
            "Mana Confluence",  # Painland
            "City of Brass",  # Painland
            "Multiversal Passage",  # Basic shockland, you choose 1 basic land type for it to be
        ],
    )
    parser.add_argument(
        "--disable_specific_lands",
        type=str,
        nargs="*",
        default=[],
        help="Disable specific lands (exact names)",
    )
    parser.add_argument("--allow_off_color_lands", action="store_true", help="Allow off-color lands")
    args = parser.parse_args()

    # Make colors uppercase and check for duplicates, validate that colors are valid (WUBRGC).
    if len(args.colors.casefold()) != len(set(args.colors.casefold())):
        msg = "Duplicate colors specified. Each color should be unique."
        raise ValueError(msg)
    args.colors = args.colors.casefold()
    valid_colors = set("wubrg")
    colorless_colors = set("c")
    if not set(args.colors).issubset(valid_colors) and not set(args.colors).issubset(colorless_colors):
        msg = "Invalid colors specified. Valid colors are [W, U, B, R, G], or C."
        raise ValueError(msg)

    # Make all group and specific land names lowercase for consistency.
    args.enable_groups = [group.casefold() for group in args.enable_groups]
    args.disable_groups = [group.casefold() for group in args.disable_groups]
    args.enable_specific_lands = [land.casefold() for land in args.enable_specific_lands]
    args.disable_specific_lands = [land.casefold() for land in args.disable_specific_lands]

    return args


# Query Scryfall API for cards based on a query string.
# Use a local cache keyed by the query hash.
# If the cache file exists, load the results from the cache instead of querying Scryfall again.
def query_scryfall(query: str) -> list[dict[str, object]]:
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()

    # Try to load the results from the cache file.
    script_dir = Path(__file__).parent
    cache_file = Path(f"{script_dir}/.cache/{query_hash}.json")
    if cache_file.exists():
        with cache_file.open("r", encoding="utf-8") as f:
            return json.load(f)["data"]

    params = {"q": query}
    response = requests.get(f"{SCRYFALL_API_URL}", params=params, headers=SCRYFALL_HEADERS, timeout=30)
    response_json = {"data": []}

    if response.status_code == HTTP_OK:
        response_json = response.json()
    else:
        print(f"Error fetching cards for query '{query}': {response.status_code}")

    if response.status_code in (200, 404):
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(response_json, f, indent=2)

    return response_json["data"]


# Get all cards from Scryfall based on groups.
def populate_cards_from_groups(groups: list[str], price_source: str) -> dict[str, list[dict[str, object]]]:
    cards_per_group = {}
    for group in groups:
        query = f"{SCRYFALL_BASE_QUERY.format(price_source=price_source)} {group}"
        data = query_scryfall(query)
        cards_per_group[group] = data
    return cards_per_group


# Get all cards from Scryfall based on exact names.
def populate_cards_from_names(names: list[str], price_source: str) -> list[dict[str, object]]:
    cards = []
    for name in names:
        query = f'{SCRYFALL_BASE_QUERY.format(price_source=price_source)} !"{name}"'
        data = query_scryfall(query)
        with suppress(StopIteration):
            cards.append(next(card for card in data if str(card["name"]).casefold() == name))
    return cards


def _is_fetchland_group(group: str | None) -> bool:
    """Return whether a group contains fetchland candidates."""
    return bool(group and (group == "otag:cycle-ala-panorama" or "fetchland" in group))


def _fetches_allowed_color(oracle_text: str, colors: str, *, allow_off_color_lands: bool) -> bool:
    """Return whether fetchland text is compatible with the deck colors."""
    basic_land_names = {"w": "Plains", "u": "Island", "b": "Swamp", "r": "Mountain", "g": "Forest"}
    matching_colors = [color for color, land in basic_land_names.items() if land in oracle_text and color in colors]
    found_colors = [color for color, land in basic_land_names.items() if land in oracle_text]
    return bool(matching_colors) if allow_off_color_lands else len(found_colors) == len(matching_colors)


def should_remove_fetchland(
    card: dict[str, object], group: str | None, colors: str, *, allow_off_color_lands: bool
) -> bool:
    if not group:
        query = f'{SCRYFALL_BASE_QUERY.format(price_source="usd")} otag:fetchland !"{card["name"]}"'
        data = query_scryfall(query)
        if data and data[0]["name"] == card["name"]:
            group = "fetchland"

    if not _is_fetchland_group(group):
        return False

    oracle_text = str(card["oracle_text"])
    return not _fetches_allowed_color(oracle_text, colors, allow_off_color_lands=allow_off_color_lands)


# Function to check if the color identity of a card matches the deck's colors (is a subset of the deck's colors).
# If the card has no color identity, it is considered to match any color identity.
def is_color_identity_matching(card: dict[str, object], colors: str) -> bool:
    color_identity = cast("list[str]", card.get("color_identity", []))
    if not color_identity:
        return True
    return {c.casefold() for c in color_identity}.issubset(set(colors))


# Process the cards to get their prices and filter out any that should be removed based on the user preferences.
def process_cards(
    cards: list[dict[str, object]],
    config: CardFilterConfig,
    group: str | None,
) -> dict[str, float]:
    processed_cards = {}

    for card in cards:
        # Filter out cards by color identity.
        if not is_color_identity_matching(card, config.colors):
            continue

        # Filter out cards that are off-color fetchlands (they don't contain color identity info).
        if should_remove_fetchland(card, group, config.colors, allow_off_color_lands=config.allow_off_color_lands):
            if group:
                restriction = "" if config.allow_off_color_lands else "strict "
                print(f"Removing card '{card['name']}' from group '{group}' due to {restriction}off-color restriction.")
            else:
                restriction = "" if config.allow_off_color_lands else "strict "
                print(f"Removing card '{card['name']}' due to {restriction}off-color restriction.")
            continue

        # Filter out specific lands by price.
        price = get_price(config.price_source, card)
        if group == "" and price > config.max_price_specific_lands:
            print(f"Removing card '{card['name']}' because its price is above the specific-land limit.")
            continue
        processed_cards[card["name"]] = price

    # Filter out groups by price.
    if processed_cards and group:
        average_price = sum(processed_cards.values()) / len(processed_cards)
        print(f'"{group}": {average_price:.2f}')
        if average_price > config.max_price_group_average:
            print(f"Removing group '{group}' because its average price is above the group limit.")
            return {}

    return processed_cards


def get_price(price_source: str, card: dict[str, object]) -> float:
    prices = cast("dict[str, str | None]", card["prices"])
    direct_price = prices.get(price_source)
    if direct_price is not None:
        return float(direct_price)

    possible_prices = []
    for price_name, price in prices.items():
        if price_name.startswith(price_source) and price is not None:
            possible_prices.append(float(price))
    if possible_prices:
        price = min(possible_prices)
    else:
        price = float("inf")
        print(f"Error fetching price for card '{card['name']}' with price source '{price_source}'.")

    return price


def _filter_candidates(
    args: argparse.Namespace, config: CardFilterConfig
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Load, filter, and reconcile enabled and disabled land candidates."""
    enabled_groups_cards = populate_cards_from_groups(args.enable_groups, args.price_source)
    disabled_groups_cards = populate_cards_from_groups(args.disable_groups, args.price_source)
    enabled_specific_lands_cards = populate_cards_from_names(args.enable_specific_lands, args.price_source)
    disabled_specific_lands_cards = populate_cards_from_names(args.disable_specific_lands, args.price_source)

    enabled_groups_cards = {
        group: process_cards(
            cards,
            config,
            group=group,
        )
        for group, cards in enabled_groups_cards.items()
    }
    disabled_groups_cards = {
        group: process_cards(
            cards,
            config,
            group=group,
        )
        for group, cards in disabled_groups_cards.items()
    }
    enabled_specific_lands_cards = process_cards(
        enabled_specific_lands_cards,
        config,
        group="",
    )
    disabled_specific_lands_cards = process_cards(
        disabled_specific_lands_cards,
        config,
        group="",
    )

    enabled_groups_cards = {group: cards for group, cards in enabled_groups_cards.items() if cards}
    disabled_groups_cards = {group: cards for group, cards in disabled_groups_cards.items() if cards}
    groups_cards = {group: cards for group, cards in enabled_groups_cards.items() if group not in disabled_groups_cards}
    specific_lands_cards = {
        card: price for card, price in enabled_specific_lands_cards.items() if card not in disabled_specific_lands_cards
    }
    return groups_cards, specific_lands_cards


def _add_specific_lands(
    args: argparse.Namespace, lands: list[str], total_price: float, cards: dict[str, float]
) -> float:
    """Add specific lands that fit the budget and land-count limits."""
    for card, price in cards.items():
        if total_price + price <= args.budget and len(lands) < args.total_lands - args.min_basics:
            lands.append(card)
            total_price += price
            print(f"Adding specific land '{card}' with price {price:.2f}. Total price: {total_price:.2f}.")
        elif total_price + price > args.budget:
            print(f"Skipping specific land '{card}' because it exceeds the remaining budget.")
        elif len(lands) >= args.total_lands - args.min_basics:
            print(f"Skipping specific land '{card}' because it would exceed the land count.")
    return total_price


def _add_land_groups(
    args: argparse.Namespace, lands: list[str], total_price: float, groups: dict[str, dict[str, float]]
) -> float:
    """Add complete land groups that fit the budget and land-count limits."""
    for group, cards in groups.items():
        group_total_price = sum(cards.values())
        within_budget = total_price + group_total_price <= args.budget
        within_count = len(lands) + len(cards) <= args.total_lands - args.min_basics
        if within_budget and within_count:
            lands.extend(cards.keys())
            total_price += group_total_price
            print(f"Adding {len(cards)} lands in group '{group}' with price {group_total_price:.2f}.")
        elif total_price + group_total_price > args.budget:
            print(f"Skipping group '{group}' because it exceeds the remaining budget.")
        elif len(lands) + len(cards) > args.total_lands - args.min_basics:
            print(f"Skipping group '{group}' because it would exceed the land count.")
    return total_price


def _fill_basic_lands(args: argparse.Namespace, lands: list[str]) -> None:
    """Fill remaining slots with basics matching the deck colors."""
    basic_land_names = {"w": "Plains", "u": "Island", "b": "Swamp", "r": "Mountain", "g": "Forest", "c": "Wastes"}
    while len(lands) < args.total_lands:
        for color in args.colors:
            lands.append(basic_land_names[color])
            if len(lands) >= args.total_lands:
                return


def _print_mana_base(lands: list[str], total_price: float) -> None:
    """Print the resulting mana base grouped alphabetically."""
    print(f"Final Mana Base ({len(lands)} lands, total price: {total_price:.2f}):")
    for land, count in Counter(sorted(lands)).items():
        print(f"{count} {land}")


def main() -> None:
    args = parse_arguments()
    config = CardFilterConfig(
        colors=args.colors,
        price_source=args.price_source,
        max_price_group_average=args.max_price_group_average,
        max_price_specific_lands=args.max_price_specific_lands,
        allow_off_color_lands=args.allow_off_color_lands,
    )
    groups_cards, specific_lands_cards = _filter_candidates(args, config)
    lands = []
    total_price = 0.0
    total_price = _add_specific_lands(args, lands, total_price, specific_lands_cards)
    total_price = _add_land_groups(args, lands, total_price, groups_cards)
    _fill_basic_lands(args, lands)
    _print_mana_base(lands, total_price)


if __name__ == "__main__":
    main()
