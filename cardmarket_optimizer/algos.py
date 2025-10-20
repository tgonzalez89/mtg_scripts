import json
import math
from pathlib import Path

card_list: dict[str, int] = {}
for line in Path("card_list.txt").open().read().strip().split("\n"):
    amount_str, card_name = line.split(" ", maxsplit=1)
    card_list[card_name] = card_list.get(card_name, 0) + int(amount_str)

offers_database: dict[str, list[dict[str, int | float | str]]] = json.load(Path("offers_database.json").open())

sellers_database: dict[str, float] = json.load(Path("sellers_database.json").open())

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


def average_offer_price(offers: list[dict[str, int | float | str]]) -> float:
    """Compute average price from a list of offers."""
    prices = sorted(float(offer["price"]) for offer in offers if "price" in offer)
    prices = prices[: math.ceil(len(prices) / 2)]
    return sum(prices) / len(prices) if prices else 0.0


# Sort by most amount of cards in card list and then by most expensive.
# Helps prioritizing selecting sellers with more copies of a card and cheaper sellers for expensive cards.
card_list = dict(
    sorted(
        card_list.items(),
        key=lambda x: (
            -x[1],  # Most needed first
            -average_offer_price(offers_database[x[0]]),  # Most expensive second
        ),
    )
)


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


selected_offers: dict[str, list[dict[str, int | float | str]]] = {}
selected_sellers: set[str] = set()
for card_name, amount in card_list.items():
    if card_name not in offers_database:
        continue
    selected_offers[card_name] = []
    amount_left = amount
    while amount_left > 0:
        selected_offer = get_best_offer(offers_database[card_name], amount_left, selected_sellers)
        selected_offers[card_name].append(selected_offer)
        amount_left -= selected_offer["selected_amount"]

json.dump(selected_offers, Path("selected_offers.json").open("w"), indent=2, sort_keys=True)
total_price, items_price, shipping_price, sellers = calc_total_prices(selected_offers)
print(f"{total_price=} {items_price=} {shipping_price=} {len(sellers)=}")
