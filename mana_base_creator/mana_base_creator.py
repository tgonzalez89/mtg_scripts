#!/bin/env python3

import argparse
import hashlib
import json
from collections import Counter
from contextlib import suppress
from pathlib import Path

import requests

SCRYFALL_API_URL = "https://api.scryfall.com/cards/search"
SCRYFALL_HEADERS = {"User-Agent": "MyMTGApp/1.0 (contact@example.com)", "Accept": "application/json"}
SCRYFALL_BASE_QUERY = "game:paper legal:commander order:{price_source} dir:asc"


def parse_arguments():
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
            "otag:cycle-verge",  # Tap for one color, can be tapped for the other if control one of the two corresponding basic land types
            "otag:cycle-msh-lair-dual",  # Tap for {C}, dual if control a basic or a land entered this turn
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
            'is:mdfc t:land (t:instant or t:sorcery or t:enchantment or t:creature or t:artifact) o:"may pay 3 life"',  # MDFC lands that can enter untapped if one pays 3 life
            'is:mdfc t:land (t:instant or t:sorcery or t:enchantment or t:creature or t:artifact) o:"This land enters tapped."',  # MDFC lands that enter tapped
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
        "--disable_specific_lands", type=str, nargs="*", default=[], help="Disable specific lands (exact names)"
    )
    parser.add_argument("--allow_off_color_lands", action="store_true", help="Allow off-color lands")
    # parser.add_argument('--allow_partial_groups', action='store_true', help='Allow partial groups of lands')

    args = parser.parse_args()

    # Make colors uppercase and check for duplicates, validate that colors are valid (WUBRGC).
    if len(args.colors.casefold()) != len(set(args.colors.casefold())):
        raise ValueError("Duplicate colors specified. Each color should be unique.")
    args.colors = args.colors.casefold()
    valid_colors = set("wubrg")
    colorless_colors = set("c")
    if not set(args.colors).issubset(valid_colors) and not set(args.colors).issubset(colorless_colors):
        raise ValueError("Invalid colors specified. Valid colors are [W, U, B, R, G], or C.")

    # Make all group and specific land names lowercase for consistency.
    args.enable_groups = [group.casefold() for group in args.enable_groups]
    args.disable_groups = [group.casefold() for group in args.disable_groups]
    args.enable_specific_lands = [land.casefold() for land in args.enable_specific_lands]
    args.disable_specific_lands = [land.casefold() for land in args.disable_specific_lands]

    return args


# Query Scryfall API for cards based on a query string.
# Use a cache, save results in a local directory (.cache) and save the results in a JSON file named after the hash of the query string.
# If the cache file exists, load the results from the cache instead of querying Scryfall again.
def query_scryfall(query):
    query_hash = hashlib.md5(query.encode("utf-8")).hexdigest()

    # Try to load the results from the cache file.
    script_dir = Path(__file__).parent
    cache_file = Path(f"{script_dir}/.cache/{query_hash}.json")
    if cache_file.exists():
        with cache_file.open("r", encoding="utf-8") as f:
            return json.load(f)["data"]

    params = {"q": query}
    response = requests.get(f"{SCRYFALL_API_URL}", params=params, headers=SCRYFALL_HEADERS)
    response_json = {"data": []}

    if response.status_code == 200:
        response_json = response.json()
    else:
        print(f"Error fetching cards for query '{query}': {response.status_code}")

    if response.status_code in (200, 404):
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(response_json, f, indent=2)

    return response_json["data"]


# Get all cards from Scryfall based on groups.
def populate_cards_from_groups(groups, price_source):
    cards_per_group = {}
    for group in groups:
        query = f"{SCRYFALL_BASE_QUERY.format(price_source=price_source)} {group}"
        data = query_scryfall(query)
        cards_per_group[group] = data
    return cards_per_group


# Get all cards from Scryfall based on exact names.
def populate_cards_from_names(names, price_source):
    cards = []
    for name in names:
        query = f'{SCRYFALL_BASE_QUERY.format(price_source=price_source)} !"{name}"'
        data = query_scryfall(query)
        with suppress(StopIteration):
            cards.append(next(card for card in data if card["name"].casefold() == name))
    return cards


# Check if some of the special lands are off-color and should be removed from the group.
# They are considered off-color if they are fetch lands that are not in the deck's colors at all.
# They are considered strictly off-color if they are fetch lands that fetch at least one color that is not in the deck's colors.
# To search for the strict colors of the lands, search the oracle text for the land's fetch ability and check if it contains any color that is not in the deck's colors.
def should_remove_fetchland(card, group, colors, allow_off_color_lands):
    if not group:
        # Check to see if this specific card is in Scryfall with the 'fetchland' tag. If it is, assign group to 'fetchland' so that it can be checked for off-color restrictions.
        query = f'{SCRYFALL_BASE_QUERY.format(price_source="usd")} otag:fetchland !"{card["name"]}"'
        data = query_scryfall(query)
        if data and data[0]["name"] == card["name"]:
            group = "fetchland"

    if not (group in ["otag:cycle-ala-panorama"] or "fetchland" in group):
        return False

    oracle_text = card["oracle_text"]
    basic_land_names = {
        "w": "Plains",
        "u": "Island",
        "b": "Swamp",
        "r": "Mountain",
        "g": "Forest",
    }
    if allow_off_color_lands:
        are_all_colors_off = False
        for color, basic_land in basic_land_names.items():
            if basic_land in oracle_text:
                if color in colors:
                    are_all_colors_off = False
                    break
                else:
                    are_all_colors_off = True
        if are_all_colors_off:
            return True
    else:
        for color, basic_land in basic_land_names.items():
            if color not in colors and basic_land in oracle_text:
                return True

    return False


# Function to check if the color identity of a card matches the deck's colors (is a subset of the deck's colors).
# If the card has no color identity, it is considered to match any color identity.
def is_color_identity_matching(card, colors):
    if not card.get("color_identity"):
        return True
    return {c.casefold() for c in card["color_identity"]}.issubset(set(colors))


# Process the cards to get their prices and filter out any that should be removed based on the user preferences.
def process_cards(
    cards, colors, price_source, max_price_group_average, max_price_specific_lands, allow_off_color_lands, group
):
    processed_cards = {}

    for card in cards:
        # Filter out cards by color identity.
        if not is_color_identity_matching(card, colors):
            continue

        # Filter out cards that are off-color fetchlands (they don't contain color identity info).
        if should_remove_fetchland(card, group, colors, allow_off_color_lands):
            if group:
                print(
                    f"Removing card '{card['name']}' from group '{group}' due to {'' if allow_off_color_lands else 'strict '}off-color restriction."
                )
            else:
                print(
                    f"Removing card '{card['name']}' due to {'' if allow_off_color_lands else 'strict '}off-color restriction."
                )
            continue

        # Filter out specific lands by price.
        price = get_price(price_source, card)
        if group == "" and price > max_price_specific_lands:
            print(
                f"Removing card '{card['name']}' because its price ({price:.2f}) exceeds max price of {max_price_specific_lands:.2f}."
            )
            continue
        processed_cards[card["name"]] = price

    # Filter out groups by price.
    if processed_cards and group:
        average_price = sum(processed_cards.values()) / len(processed_cards)
        print(f'"{group}": {average_price:.2f}')
        if average_price > max_price_group_average:
            print(
                f"Removing group '{group}' because its average price ({average_price:.2f}) exceeds max price of {max_price_group_average:.2f}."
            )
            return {}

    return processed_cards


def get_price(price_source, card):
    if card["prices"].get(price_source) is not None:
        return float(card["prices"][price_source])

    possible_prices = []
    for price_name, price in card["prices"].items():
        if price_name.startswith(price_source) and price is not None:
            possible_prices.append(float(price))
    if possible_prices:
        price = min(possible_prices)
    else:
        price = float("inf")
        print(
            f"Error fetching price for card '{card['name']}' with price source '{price_source}'. Defaulting to infinity."
        )

    return price


def main():
    args = parse_arguments()
    enabled_groups_cards = populate_cards_from_groups(args.enable_groups, args.price_source)
    disabled_groups_cards = populate_cards_from_groups(args.disable_groups, args.price_source)
    enabled_specific_lands_cards = populate_cards_from_names(args.enable_specific_lands, args.price_source)
    disabled_specific_lands_cards = populate_cards_from_names(args.disable_specific_lands, args.price_source)

    # print("{")
    # print('"Enabled Groups Cards":', json.dumps(enabled_groups_cards, indent=2) + ",")
    # print('"Disabled Groups Cards":', json.dumps(disabled_groups_cards, indent=2) + ",")
    # print('"Enabled Specific Lands Cards":', json.dumps(enabled_specific_lands_cards, indent=2) + ",")
    # print('"Disabled Specific Lands Cards":', json.dumps(disabled_specific_lands_cards, indent=2))
    # print("}")

    enabled_groups_cards = {
        group: process_cards(
            cards,
            args.colors,
            args.price_source,
            args.max_price_group_average,
            args.max_price_specific_lands,
            args.allow_off_color_lands,
            group,
        )
        for group, cards in enabled_groups_cards.items()
    }
    disabled_groups_cards = {
        group: process_cards(
            cards,
            args.colors,
            args.price_source,
            args.max_price_group_average,
            args.max_price_specific_lands,
            args.allow_off_color_lands,
            group,
        )
        for group, cards in disabled_groups_cards.items()
    }
    enabled_specific_lands_cards = process_cards(
        enabled_specific_lands_cards,
        args.colors,
        args.price_source,
        args.max_price_group_average,
        args.max_price_specific_lands,
        args.allow_off_color_lands,
        "",
    )
    disabled_specific_lands_cards = process_cards(
        disabled_specific_lands_cards,
        args.colors,
        args.price_source,
        args.max_price_group_average,
        args.max_price_specific_lands,
        args.allow_off_color_lands,
        "",
    )

    # print("{")
    # print('"Enabled Groups Cards":', json.dumps(enabled_groups_cards, indent=2) + ",")
    # print('"Disabled Groups Cards":', json.dumps(disabled_groups_cards, indent=2) + ",")
    # print('"Enabled Specific Lands Cards":', json.dumps(enabled_specific_lands_cards, indent=2) + ",")
    # print('"Disabled Specific Lands Cards":', json.dumps(disabled_specific_lands_cards, indent=2))
    # print("}")

    # Remove empty groups from the enabled and disabled groups dictionaries.
    enabled_groups_cards = {group: cards for group, cards in enabled_groups_cards.items() if cards}
    disabled_groups_cards = {group: cards for group, cards in disabled_groups_cards.items() if cards}

    # Get the final groups of cards and specific lands after filtering out the disabled groups and specific lands.
    groups_cards = {group: cards for group, cards in enabled_groups_cards.items() if group not in disabled_groups_cards}
    specific_lands_cards = {
        card: price for card, price in enabled_specific_lands_cards.items() if card not in disabled_specific_lands_cards
    }

    # Create the mana base based on the filtered groups and specific lands, while respecting the budget and number of basic lands.
    lands = []
    total_price = 0.0

    # Add specific lands.
    for card, price in specific_lands_cards.items():
        if total_price + price <= args.budget and len(lands) < args.total_lands - args.min_basics:
            lands.append(card)
            total_price += price
            print(
                f"Adding specific land '{card}' with price {price:.2f}. Total price: {total_price:.2f}. Total lands: {len(lands) + args.min_basics}."
            )
        elif total_price + price > args.budget:
            print(
                f"Skipping specific land '{card}' because its price ({price:.2f}) exceeds remaining budget ({args.budget - total_price:.2f})."
            )
        elif len(lands) >= args.total_lands - args.min_basics:
            print(
                f"Skipping specific land '{card}' because adding it to the current land count ({len(lands) + args.min_basics}) would exceed the total number of lands ({args.total_lands})."
            )

    # Add groups of lands. Don't allow for partial groups. If the total price of the group exceeds the budget, skip the group entirely.
    for group, cards in groups_cards.items():
        group_total_price = sum(cards.values())
        if (
            total_price + group_total_price <= args.budget
            and len(lands) + len(cards) <= args.total_lands - args.min_basics
        ):
            lands.extend(cards.keys())
            total_price += group_total_price
            print(
                f"Adding {len(cards)} lands in group '{group}' with price {group_total_price:.2f}. Total price: {total_price:.2f}. Total lands: {len(lands) + args.min_basics}."
            )
        elif total_price + group_total_price > args.budget:
            print(
                f"Skipping group '{group}' because its total price ({group_total_price:.2f}) exceeds remaining budget ({args.budget - total_price:.2f})."
            )
        elif len(lands) + len(cards) > args.total_lands - args.min_basics:
            print(
                f"Skipping group '{group}' because adding its lands ({len(cards)}) to the current land count ({len(lands) + args.min_basics}) would exceed the total number of lands ({args.total_lands})."
            )

    # Fill the rest with basic lands of the deck's colors.
    basic_land_names = {
        "w": "Plains",
        "u": "Island",
        "b": "Swamp",
        "r": "Mountain",
        "g": "Forest",
        "c": "Wastes",
    }
    while len(lands) < args.total_lands:
        for color in args.colors:
            basic_land_name = basic_land_names[color]
            lands.append(basic_land_name)
            if len(lands) >= args.total_lands:
                break
    print(f"Final Mana Base ({len(lands)} lands, total price: {total_price:.2f}):")

    # Alphabetically sort the lands and print them with their counts.
    lands.sort()
    land_counts = Counter(lands)
    for land, count in land_counts.items():
        print(f"{count} {land}")


if __name__ == "__main__":
    main()
