import argparse
import json
import math
import re
from pathlib import Path
from typing import TYPE_CHECKING, Final, NotRequired, TypedDict

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

MIN_CARD_FIELDS: Final = 2


class OfferRecord(TypedDict):
    total_price: float
    price: float
    shipping_price: float
    amount: int
    seller: str


class SelectedOfferRecord(OfferRecord):
    selected_amount: NotRequired[int]
    price_per_card: NotRequired[float]
    card_name: NotRequired[str]


class SellerAvailability(TypedDict):
    shipping_price: float
    cards_available: int


def write_json(path: Path, data: Mapping[str, object] | Sequence[object]) -> None:
    """Write JSON data with a managed file handle."""
    with path.open("w", encoding="utf-8") as output_file:
        json.dump(data, output_file, indent=2, sort_keys=True)


def parse_args() -> argparse.Namespace:
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

    return parser.parse_args()


args = parse_args()

card_list: dict[str, int] = {}
with Path(args.card_list).open("r", encoding="utf-8") as fp:
    for raw_line in fp:
        pattern = re.compile(r"\s+")
        line = pattern.sub(" ", raw_line).strip()
        card_name = line
        amount = 1
        parts = line.split(" ", maxsplit=1)
        if len(parts) == MIN_CARD_FIELDS and parts[0].isdigit():
            card_name = parts[1]
            amount = int(parts[0])
        if len(card_name) > 0:
            card_name = re.sub(r"(.*?[^/]) *//? *([^/].*)", r"\1 // \2", card_name).lower()
            card_list[card_name] = card_list.get(card_name, 0) + amount

with Path(args.offers_database).open("r", encoding="utf-8") as offers_file:
    offers_database: dict[str, list[SelectedOfferRecord]] = json.load(offers_file)

with Path(args.sellers_database).open("r", encoding="utf-8") as sellers_file:
    sellers_database: dict[str, float] = json.load(sellers_file)

sellers_db_cards_available: dict[str, SellerAvailability] = {
    seller: {"shipping_price": shipping_price, "cards_available": 0}
    for seller, shipping_price in sellers_database.items()
}
for card_name, amount in card_list.items():
    if card_name not in offers_database:
        continue
    for offer in offers_database[card_name]:
        selected_amount = min(int(offer["amount"]), amount)
        if offer["seller"] not in sellers_database:
            sellers_db_cards_available[str(offer["seller"])] = {
                "shipping_price": float(offer["shipping_price"]),
                "cards_available": 0,
            }
        sellers_db_cards_available[str(offer["seller"])]["cards_available"] += selected_amount


def calc_total_prices(
    selected_offers: dict[str, list[SelectedOfferRecord]],
) -> tuple[float, float, float, set[str]]:
    total_price = 0.0
    items_price = 0.0
    shipping_price = 0.0
    seen_sellers: set[str] = set()

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


def average_offer_by_key(offers: list[SelectedOfferRecord], key: str) -> float:
    """Compute average of 'key' from a list of offers."""
    prices = sorted(float(dict(offer)[key]) for offer in offers if key in offer)
    prices = prices[: math.ceil(len(prices) / 2)]
    return round(sum(prices) / len(prices), 2) if prices else 0.0


def get_best_offer(
    offers: list[SelectedOfferRecord], amount: int, selected_sellers: set[str]
) -> SelectedOfferRecord | None:
    # Beware: This function modifies the offers list and the items inside it.
    for offer in offers:
        # Select amount of cards needed from this offer.
        selected_amount = min(int(offer["amount"]), amount)
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
    offers_database: dict[str, list[SelectedOfferRecord]],
    selected_offers: dict[str, list[SelectedOfferRecord]] | None = None,
    selected_sellers: set[str] | None = None,
) -> tuple[dict[str, list[SelectedOfferRecord]], set[str]]:
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
            if selected_offer is None:
                break
            selected_offers[card_name].append(selected_offer)
            amount_left -= int(selected_offer["selected_amount"])

    return selected_offers, selected_sellers


selected_offers, selected_sellers = run_algo(card_list, offers_database)


selected_offers_by_seller: dict[str, list[SelectedOfferRecord]] = {}
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

with Path(args.offers_database).open("r", encoding="utf-8") as offers_file:
    offers_database = json.load(offers_file)

selected_offers, selected_sellers = run_algo(new_card_list, offers_database, selected_offers, selected_sellers)
write_json(Path(args.selected_offers), selected_offers)
total_price, items_price, shipping_price, sellers = calc_total_prices(selected_offers)
print(f"{total_price=} {items_price=} {shipping_price=} {len(sellers)=}")
