import argparse
import copy
import csv
import json
import re
import urllib.request
from pathlib import Path

DEBUG_JSON = False  # Set to True to enable saving intermediate data as json files


def parse_deck_id_arg(deck_id_list):
    """
    Parses a list of strings into a tuple of deck IDs.
    Supports nested tuples using parentheses, e.g. "(id1,id2)".
    """
    result = []
    for item in deck_id_list:
        item = item.strip()
        # Allow both (id1,id2) and simple id forms
        if item.startswith("(") and item.endswith(")"):
            # Safely parse content inside parentheses as a tuple of strings
            inner = item[1:-1].strip()
            ids = tuple(i.strip() for i in inner.split(",") if i.strip())
            result.append(ids)
        else:
            result.append(item)
    return tuple(result)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--owned-file",
        "-o",
        required=True,
        help=(
            "Path to the owned cards file (required). "
            "Export it from https://moxfield.com/collection (More -> Export CSV)."
        ),
    )

    parser.add_argument(
        "--purchased-file",
        "-p",
        default="purchased.txt",
        help=(
            "Path to the purchased cards file (default: purchased.txt). "
            "Populate by copy-pasting the list of cards from https://www.cardtrader.com/orders/buyer_future_order."
        ),
    )

    parser.add_argument(
        "--want-deck-ids",
        "-w",
        nargs="+",
        required=True,
        help="Moxfield deck IDs you want cards for. Group variants using parentheses, e.g. '(id1,id2)'.",
    )

    parser.add_argument(
        "--have-deck-ids",
        "-v",
        nargs="*",
        default=[],
        help="Moxfield deck IDs you already have. Group variants using parentheses, e.g. '(id3,id4)'.",
    )

    parser.add_argument(
        "--buy-considering",
        "-b",
        action="store_true",
        default=True,
        help="Whether to buy cards in the considering pile.",
    )

    parser.add_argument(
        "--to-purchase-file",
        default="to_purchase.txt",
        help="Path to output file listing all cards to purchase (default: to_purchase.txt).",
    )

    parser.add_argument(
        "--to-purchase-decks-file",
        default="to_purchase_decks.txt",
        help="Path to output file listing cards to purchase for decks (default: to_purchase_decks.txt).",
    )

    parser.add_argument(
        "--to-purchase-considering-file",
        default="to_purchase_considering.txt",
        help="Path to output file listing cards to purchase from the considering pile (default: to_purchase_considering.txt).",
    )

    args = parser.parse_args()

    args.want_deck_ids = parse_deck_id_arg(args.want_deck_ids)
    args.have_deck_ids = parse_deck_id_arg(args.have_deck_ids)

    return args


def parse_owned_file(path: str) -> dict[str, int]:
    """
    Parse a Moxfield-owned cards CSV file and consolidate duplicate cards.

    Args:
        path (str): Path to the owned CSV file exported from Moxfield.

    Returns:
        dict[str, int]: A dictionary mapping card names to total owned counts.
    """
    owned_counts: dict[str, int] = {}

    with Path(path).open() as csvfile:
        reader = csv.DictReader(csvfile)

        # Try to detect column names dynamically (Moxfield can change headers)
        name_field = None
        count_field = None

        assert reader.fieldnames is not None
        for field in reader.fieldnames:
            if field.lower() == "name":
                name_field = field
            elif field.lower() == "count":
                count_field = field

        if not name_field or not count_field:
            raise ValueError(f"Expected columns 'Name' and 'Count' not found in {path}")

        # Consolidate duplicates by name
        for row in reader:
            name = row[name_field].strip().lower()
            try:
                count = int(row[count_field])
            except ValueError:
                count = 0
            owned_counts[name] = owned_counts.get(name, 0) + count

    return owned_counts


args = parse_args()


# Get purchased cards.

purchased_cards: dict[str, int] = {}
if args.purchased_file is not None:
    with Path(args.purchased_file).open() as f:
        text = f.read()
    pattern = re.compile(r"([^\n]+)\s+\w+ (\d+)\s+\1", re.DOTALL)
    matches = pattern.findall(text)
    if len(matches) > 0:
        for match in matches:
            card_name = match[0].strip()
            amount = int(match[1].strip())
            card_name = re.sub(r"(.*?[^/]) *//? *([^/].*)", r"\1 // \2", card_name).lower()
            purchased_cards[card_name] = purchased_cards.get(card_name, 0) + amount
    else:
        for line in text.splitlines():
            pattern = re.compile(r"\s+")
            line = pattern.sub(" ", line).strip()
            card_name = line
            amount = 1
            parts = line.split(" ", maxsplit=1)
            if len(parts) == 2:
                if parts[0].isdigit():
                    card_name = parts[1]
                    amount = int(parts[0])
            if len(card_name) > 0:
                card_name = re.sub(r"(.*?[^/]) *//? *([^/].*)", r"\1 // \2", card_name).lower()
                purchased_cards[card_name] = purchased_cards.get(card_name, 0) + amount


if DEBUG_JSON:
    json.dump(purchased_cards, Path("purchased.json").open("w"), indent=2, sort_keys=True)

# Get owned cards.

owned_cards = parse_owned_file(args.owned_file)

if DEBUG_JSON:
    json.dump(owned_cards, Path("owned.json").open("w"), indent=2, sort_keys=True)

# Calculate the cards that I have.

have = copy.copy(owned_cards)
for card_name, amount in purchased_cards.items():
    if card_name not in have:
        have[card_name] = amount
    else:
        have[card_name] += amount

if DEBUG_JSON:
    json.dump(have, Path("have.json").open("w"), indent=2, sort_keys=True)


# Get decks


def download_deck(deck_id) -> tuple[dict[str, int], dict[str, int]]:
    moxfield_api_url = "https://api.moxfield.com/v2/decks/all/"
    headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"}
    request = urllib.request.Request(moxfield_api_url + deck_id, headers=headers)
    with urllib.request.urlopen(request) as response:
        if response.status != 200:
            print(f"Failed to get data using urllib. Status code: {response.status_code}")
            exit()
        encoding = response.headers.get_content_charset("utf-8")
        data = json.loads(response.read().decode(encoding))
        if DEBUG_JSON:
            json.dump(data, Path(deck_id + ".json").open("w"), indent=2, sort_keys=True)
    deck = {card_name.lower(): card_data["quantity"] for card_name, card_data in data["commanders"].items()}
    for card_name, card_data in data["sideboard"].items():
        deck[card_name.lower()] = deck.get(card_name.lower(), 0) + card_data["quantity"]
    for card_name, card_data in data["companions"].items():
        deck[card_name.lower()] = deck.get(card_name.lower(), 0) + card_data["quantity"]
    for card_name, card_data in data["mainboard"].items():
        deck[card_name.lower()] = deck.get(card_name.lower(), 0) + card_data["quantity"]
    maybeboard = {card_name.lower(): card_data["quantity"] for card_name, card_data in data["maybeboard"].items()}
    return deck, maybeboard


cards_in_decks: dict[str, int] = {}
considering_cards: dict[str, int] = {}
for deck_id in args.want_deck_ids + args.have_deck_ids:
    if isinstance(deck_id, tuple):
        main_decks = []
        maybeboards = []
        for dck_id in deck_id:
            mdck, mbbd = download_deck(dck_id)
            main_decks.append(mdck)
            maybeboards.append(mbbd)
        main_deck: dict[str, int] = {}
        maybeboard: dict[str, int] = {}
        for mdck in main_decks:
            for card_name, amount in mdck.items():
                main_deck[card_name] = max(main_deck.get(card_name, 0), amount)
        for mbbd in maybeboards:
            for card_name, amount in mbbd.items():
                maybeboard[card_name] = max(maybeboard.get(card_name, 0), amount)
    else:
        main_deck, maybeboard = download_deck(deck_id)

    for card_name, amount in main_deck.items():
        if deck_id in args.have_deck_ids and card_name in have:
            if have[card_name] > amount:
                # I have more than I am using for the deck. Subtract from 'have' the amount I'm using in the deck.
                have[card_name] -= amount
            else:
                # I have the exact amount I need for the deck or less. Remove card from 'have'.
                have.pop(card_name)
        else:
            cards_in_decks[card_name] = cards_in_decks.get(card_name, 0) + amount
    if deck_id not in args.have_deck_ids:
        for card_name, amount in maybeboard.items():
            considering_cards[card_name] = considering_cards.get(card_name, 0) + amount

if DEBUG_JSON:
    json.dump(cards_in_decks, Path("in_decks.json").open("w"), indent=2, sort_keys=True)
    json.dump(considering_cards, Path("considering.json").open("w"), indent=2, sort_keys=True)

# Calculate the cards that I need.

need = copy.copy(cards_in_decks)
need_decks = copy.copy(cards_in_decks)
need_considering = {}
if args.buy_considering:
    for card_name, amount in considering_cards.items():
        if card_name not in need:
            # Only add 1 copy of each card from considering and only if it is not already in the decks.
            # TODO: Rethink this. This works for Commander decks because they are singleton.
            #       For normal decks we need the max amount found across maybeboards.
            #       If there are more in some maybeboard than in each deck, we need to add the difference
            #       between the max across maybeboards and the max across decks.
            need[card_name] = 1
            need_considering[card_name] = 1

if DEBUG_JSON:
    json.dump(need, Path("need.json").open("w"), indent=2, sort_keys=True)
    json.dump(need_decks, Path("need_decks.json").open("w"), indent=2, sort_keys=True)
    json.dump(need_considering, Path("need_considering.json").open("w"), indent=2, sort_keys=True)

# Calculate the cards that I need to buy by filtering out cards that I own or already purchased from the cards that I need.

to_purchase = {}
avoided = {}
avoided_owned = {}
avoided_purchased = {}
for card_name, amount in need.items():
    if card_name not in have:
        to_purchase[card_name] = amount
    elif amount > have[card_name]:
        to_purchase[card_name] = amount - have[card_name]
        avoided[card_name] = have[card_name]
        if card_name in purchased_cards:
            avoided_purchased[card_name] = purchased_cards[card_name]
        if card_name in owned_cards:
            avoided_owned[card_name] = owned_cards[card_name]
    else:
        avoided[card_name] = amount
        left = amount
        if card_name in purchased_cards:
            avoided_purchased[card_name] = min(amount, purchased_cards[card_name])
        if card_name in owned_cards and amount - avoided_purchased.get(card_name, 0) > 0:
            avoided_owned[card_name] = amount - avoided_purchased.get(card_name, 0)

if DEBUG_JSON:
    json.dump(avoided, Path("avoided.json").open("w"), indent=2, sort_keys=True)
    json.dump(avoided_owned, Path("avoided_owned.json").open("w"), indent=2, sort_keys=True)
    json.dump(avoided_purchased, Path("avoided_purchased.json").open("w"), indent=2, sort_keys=True)

with Path(args.to_purchase).open("w") as f:
    for card_name, amount in sorted(to_purchase.items()):
        f.write(f"{amount} {card_name}\n")

to_purchase_decks = {}
for card_name, amount in need_decks.items():
    if card_name not in have:
        to_purchase_decks[card_name] = amount
    else:
        if have[card_name] < amount:
            to_purchase_decks[card_name] = amount - have[card_name]

with Path(args.to_purchase_decks.txt).open("w") as f:
    for card_name, amount in sorted(to_purchase_decks.items()):
        f.write(f"{amount} {card_name}\n")

to_purchase_considering = {}
for card_name, amount in need_considering.items():
    if card_name not in have:
        to_purchase_considering[card_name] = amount
    else:
        if have[card_name] < amount:
            to_purchase_considering[card_name] = amount - have[card_name]

if args.buy_considering:
    with Path(args.to_purchase_considering.txt).open("w") as f:
        for card_name, amount in sorted(to_purchase_considering.items()):
            f.write(f"{amount} {card_name}\n")
