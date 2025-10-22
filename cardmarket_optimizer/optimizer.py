import argparse
import json
import math
import re
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--card-list",
        "-c",
        default="card_list.txt",
        help="Path to input text file containing the card list (default card_list.txt).",
    )
    parser.add_argument(
        "--sellers-database",
        "-s",
        default="sellers_database.json",
        help="Path to input sellers database file (default sellers_database.json).",
    )
    parser.add_argument(
        "--offers-database",
        "-o",
        default="offers_database.json",
        help="Path to input offers database file (default offers_database.json).",
    )
    parser.add_argument(
        "--selected-offers",
        "-e",
        default="selected_offers.json",
        help="Path to output selected offers file (default selected_offers.json).",
    )

    args = parser.parse_args()
    return args


args = parse_args()

card_list: dict[str, int] = {}
with Path(args.card_list).open() as fp:
    for line in fp:
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
            card_list[card_name] = card_list.get(card_name, 0) + amount

offers_database: dict[str, list[dict[str, int | float | str]]] = json.load(Path(args.offers_database).open())

sellers_database: dict[str, float] = json.load(Path(args.sellers_database).open())

sellers_db_cards_available: dict[str, dict[str, int | float]] = {
    seller: {"shipping_price": shipping_price, "cards_available": 0}
    for seller, shipping_price in sellers_database.items()
}
for card_name, amount in card_list.items():
    if card_name not in offers_database:
        continue
    for offer in offers_database[card_name]:
        selected_amount = int(offer["amount"]) if amount >= int(offer["amount"]) else amount
        if offer["seller"] not in sellers_database:
            sellers_db_cards_available[str(offer["seller"])] = {
                "shipping_price": float(offer["shipping_price"]),
                "cards_available": 0,
            }
        sellers_db_cards_available[str(offer["seller"])]["cards_available"] += selected_amount


def calc_total_prices(selected_offers: dict[str, list[dict[str, int | float | str]]]):
    total_price = 0.0
    items_price = 0.0
    shipping_price = 0.0
    seen_sellers = set()

    for offers in selected_offers.values():
        for offer in offers:
            offer_items_price = float(offer["price"]) * int(offer["selected_amount"])
            if offer["seller"] not in seen_sellers:
                offer_shipping_price = float(offer["shipping_price"])
                seen_sellers.add(offer["seller"])
            else:
                offer_shipping_price = 0.0
            offer_total_price = offer_items_price + offer_shipping_price
            total_price += offer_total_price
            items_price += offer_items_price
            shipping_price += offer_shipping_price

    return round(total_price, 2), round(items_price, 2), round(shipping_price, 2), seen_sellers


# ALGORITHM: Before running the algorithm, sort the cards by amount and then by price.
#            Selects as many as possible for each offer. Then calculates the total price for each offer.
#            Then calculates the per-card price for each offer. Then orders the offers by per-card price.
#            Then selects the cheapest one, and if tied the one with the seller with most cards.
#            Then calculates the remaining needed amount. Then does the whole process again until we buy all needed cards.
#            Takes into account that if the card is from a seller that was selected previously,
#            the shipping should be effectively free for this card, since the shipping was already considered previously.


def average_offer_by_key(offers: list[dict[str, int | float | str]], key: str) -> float:
    """Compute average of 'key' from a list of offers."""
    prices = sorted(float(offer[key]) for offer in offers if key in offer)
    prices = prices[: math.ceil(len(prices) / 2)]
    return round(sum(prices) / len(prices), 2) if prices else 0.0


def get_best_offer(offers: list[dict[str, int | float | str]], amount: int, selected_sellers: set[str]):
    # Beware: This function modifies the offers list and the items inside it.
    for offer in offers:
        # Select amount of cards needed from this offer.
        selected_amount = int(offer["amount"]) if amount >= int(offer["amount"]) else amount
        offer["selected_amount"] = selected_amount
        # Calculate the price per card. Using only the number of cards actually available from the seller.
        shipping_price = float(offer["shipping_price"]) if offer["seller"] not in selected_sellers else 0.0
        total_price_selected_amount = round(float(offer["price"]) * selected_amount + shipping_price, 2)
        offer["price_per_card"] = round(total_price_selected_amount / selected_amount, 2)
    # Sort cards by price per card and then by biggest sellers.
    # Then selects the first one of the list and removes it so that it's not considered in the next iteration.
    offers.sort(
        key=lambda x: (x["price_per_card"], -int(sellers_db_cards_available[str(x["seller"])]["cards_available"])),
    )
    selected_offer = offers.pop(0)
    selected_sellers.add(str(selected_offer["seller"]))
    return selected_offer


def run_algo(
    card_list: dict[str, int],
    offers_database: dict[str, list[dict[str, int | float | str]]],
    selected_offers: dict[str, list[dict[str, int | float | str]]] | None = None,
    selected_sellers: set[str] | None = None,
) -> tuple[dict[str, list[dict[str, int | float | str]]], set[str]]:
    # Sort by least offers, then most amount of cards in card list and then by most expensive.
    # Helps prioritizing selecting sellers with more copies of a card and cheaper sellers for expensive cards.
    card_list = dict(
        sorted(
            card_list.items(),
            key=lambda x: (
                len(offers_database[x[0]]),  # Least offers
                -x[1],  # Most needed
                -average_offer_by_key(offers_database[x[0]], "price"),  # Most expensive
            ),
        )
    )

    if selected_offers is None:
        selected_offers = {}
    if selected_sellers is None:
        selected_sellers = set()
    for card_name, amount in card_list.items():
        if card_name not in offers_database:
            continue
        selected_offers[card_name] = []
        amount_left = amount
        while amount_left > 0:
            selected_offer = get_best_offer(offers_database[card_name], amount_left, selected_sellers)
            selected_offers[card_name].append(selected_offer)
            amount_left -= selected_offer["selected_amount"]

    return selected_offers, selected_sellers


selected_offers, selected_sellers = run_algo(card_list, offers_database)


# Get the sellers with only 1 item and try to see if we can reassign that item to a different, but already-selected seller
# so that we can save the shipping of the current seller.


selected_offers_by_seller: dict[str, list[dict[str, int | float | str]]] = {}
for card_name, offers in selected_offers.items():
    for offer in offers:
        if offer["seller"] not in selected_offers_by_seller:
            selected_offers_by_seller[str(offer["seller"])] = []
        offer["card_name"] = card_name
        selected_offers_by_seller[str(offer["seller"])].append(offer)

new_card_list: dict[str, int] = {}
for seller, offers in selected_offers_by_seller.items():
    if sum(int(offer["selected_amount"]) for offer in offers) == 1:
        selected_sellers.remove(seller)
        new_card_list[str(offers[0]["card_name"])] = 1
        for card_name, sel_ofrs in tuple(selected_offers.items()):
            for i, sel_ofr in enumerate(sel_ofrs):
                if offers[0] == sel_ofr:
                    sel_ofrs.pop(i)
                    if len(sel_ofrs) == 0:
                        selected_offers.pop(card_name)

offers_database = json.load(Path(args.offers_database).open())

selected_offers, selected_sellers = run_algo(new_card_list, offers_database, selected_offers, selected_sellers)
json.dump(selected_offers, Path(args.selected_offers).open("w"), indent=2, sort_keys=True)
total_price, items_price, shipping_price, sellers = calc_total_prices(selected_offers)
print(f"{total_price=} {items_price=} {shipping_price=} {len(sellers)=}")
