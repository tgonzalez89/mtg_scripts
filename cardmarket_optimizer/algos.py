import json
import math
import random
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
        assert isinstance(offer["amount"], int)
        selected_amount = offer["amount"] if amount >= offer["amount"] else amount
        if str(offer["seller"]) not in sellers_database:
            sellers_db_cards_available[str(offer["seller"])] = {
                "shipping_price": float(offer["shipping_price"]),
                "cards_available": 0,
            }
        sellers_db_cards_available[str(offer["seller"])]["cards_available"] += selected_amount

selected_offers: dict[str, list[dict[str, int | float | str]]]
selected_sellers: set[str]


def calc_total_prices(selected_offers: dict[str, list[dict[str, int | float | str]]]):
    total_price = 0.0
    items_price = 0.0
    shipping_price = 0.0
    seen_sellers = set()

    for offers in selected_offers.values():
        for offer in offers:
            assert isinstance(offer["price"], float)
            assert isinstance(offer["shipping_price"], float)
            assert isinstance(offer["selected_amount"], int)
            offer_items_price = offer["price"] * offer["selected_amount"]
            if offer["seller"] not in seen_sellers:
                offer_shipping_price = offer["shipping_price"]
                seen_sellers.add(offer["seller"])
            else:
                offer_shipping_price = 0.0
            offer_total_price = offer_items_price + offer_shipping_price
            total_price += offer_total_price
            items_price += offer_items_price
            shipping_price += offer_shipping_price

    return round(total_price, 2), round(items_price, 2), round(shipping_price, 2), seen_sellers


# ALGORITHM 1: Selects from the cheapest offer until the amount required for the card is fulfilled.
#              Selects as many as possible from each offer before moving on to the next one. This helps a little with shipping costs.
#              Disregards that shipping costs remain flat even though a seller with a higher item price could have more copies.
#              Disregards how bundling together different cards with the same seller keeps shipping costs flat.


offers_database = json.load(Path("offers_database.json").open())
for card_name in offers_database:
    offers_database[card_name] = sorted(
        offers_database[card_name],
        key=lambda x: (-int(sellers_db_cards_available[str(x["seller"])]["cards_available"]), x["total_price"]),
    )
selected_offers = {}
for card_name, amount in card_list.items():
    if card_name not in offers_database:
        continue
    selected_offers[card_name] = []
    amount_left = amount
    for offer in sorted(offers_database[card_name], key=lambda x: x["total_price"]):
        assert isinstance(offer["amount"], int)
        if amount_left >= offer["amount"]:
            offer["selected_amount"] = offer["amount"]
            amount_left -= offer["amount"]
        else:
            offer["selected_amount"] = amount_left
            amount_left = 0
        selected_offers[card_name].append(offer)
        if amount_left <= 0:
            break

json.dump(selected_offers, Path("algo1.json").open("w"), indent=2)
total_price, items_price, shipping_price, sellers = calc_total_prices(selected_offers)
print(f"Algo 1: {total_price=} {items_price=} {shipping_price=} {len(sellers)=}")


# ALGORITHM 2: Selects as many as possible for each offer. Then calculates the total price for each offer.
#              Then calculates the per card price for each offer. Then orders the offers by per card price.
#              Then selects the cheapest one. Then calculates the remaining needed amount. Then does the whole process again.
#              Takes into account that if the card is from a seller that was selected previously,
#              the shipping should be effectively free for this card, since the shipping was already considered previously.
#              Disregards how bundling together different cards with the same seller keeps shipping costs flat.


def get_best_offer(offers_database: dict[str, list[dict[str, int | float | str]]], card_name: str, amount: int):
    for offer in offers_database[card_name]:
        assert isinstance(offer["amount"], int)
        assert isinstance(offer["price"], float)
        assert isinstance(offer["shipping_price"], float)
        offer["selected_amount"] = offer["amount"] if amount >= offer["amount"] else amount
        assert isinstance(offer["selected_amount"], int)
        offer["total_price_selected_amount"] = round(
            offer["price"] * offer["selected_amount"] + offer["shipping_price"], 2
        )
        assert isinstance(offer["total_price_selected_amount"], float)
        offer["price_per_card"] = round(offer["total_price_selected_amount"] / offer["selected_amount"], 2)
    offers_database[card_name] = sorted(offers_database[card_name], key=lambda x: x["price_per_card"])
    selected_offer = offers_database[card_name].pop(0)
    return selected_offer


offers_database = json.load(Path("offers_database.json").open())
for card_name in offers_database:
    offers_database[card_name] = sorted(
        offers_database[card_name],
        key=lambda x: (-int(sellers_db_cards_available[str(x["seller"])]["cards_available"]), x["total_price"]),
    )
selected_offers = {}
for card_name, amount in card_list.items():
    if card_name not in offers_database:
        continue
    selected_offers[card_name] = []
    amount_left = amount
    while amount_left > 0:
        selected_offer = get_best_offer(offers_database, card_name, amount_left)
        selected_offers[card_name].append(selected_offer)
        amount_left -= selected_offer["selected_amount"]

json.dump(selected_offers, Path("algo2.json").open("w"), indent=2)
total_price, items_price, shipping_price, sellers = calc_total_prices(selected_offers)
print(f"Algo 2: {total_price=} {items_price=} {shipping_price=} {len(sellers)=}")


# ALGORITHM 3: Uses algorithm's 2 method but checks if the seller has been previously selected for an offer.
#              Takes into account that if the card is from a seller that was selected previously,
#              the shipping should be effectively free for this card, since the shipping was already considered previously.


def get_best_offer_use_selected_sellers(
    offers_database: dict[str, list[dict[str, int | float | str]]], card_name: str, amount: int
):
    for offer in offers_database[card_name]:
        assert isinstance(offer["amount"], int)
        assert isinstance(offer["price"], float)
        assert isinstance(offer["shipping_price"], float)
        offer["selected_amount"] = offer["amount"] if amount >= offer["amount"] else amount
        assert isinstance(offer["selected_amount"], int)
        shipping_price = offer["shipping_price"] if offer["seller"] not in selected_sellers else 0.0
        offer["total_price_selected_amount"] = round(offer["price"] * offer["selected_amount"] + shipping_price, 2)
        assert isinstance(offer["total_price_selected_amount"], float)
        offer["price_per_card"] = round(offer["total_price_selected_amount"] / offer["selected_amount"], 2)
    offers_database[card_name] = sorted(offers_database[card_name], key=lambda x: x["price_per_card"])
    selected_offer = offers_database[card_name].pop(0)
    selected_sellers.add(str(selected_offer["seller"]))
    return selected_offer


offers_database = json.load(Path("offers_database.json").open())
for card_name in offers_database:
    offers_database[card_name] = sorted(
        offers_database[card_name],
        key=lambda x: (-int(sellers_db_cards_available[str(x["seller"])]["cards_available"]), x["total_price"]),
    )
selected_offers = {}
selected_sellers = set()
for card_name, amount in card_list.items():
    if card_name not in offers_database:
        continue
    selected_offers[card_name] = []
    amount_left = amount
    while amount_left > 0:
        selected_offer = get_best_offer_use_selected_sellers(offers_database, card_name, amount_left)
        selected_offers[card_name].append(selected_offer)
        amount_left -= selected_offer["selected_amount"]

json.dump(selected_offers, Path("algo3.json").open("w"), indent=2)
total_price, items_price, shipping_price, sellers = calc_total_prices(selected_offers)
print(f"Algo 3: {total_price=} {items_price=} {shipping_price=} {len(sellers)=}")


# ALGORITHM 4: Uses algorithm's 3 method but first orders cards by amount and by price.


def average_offer_price(offers: list[dict[str, int | float | str]]) -> float:
    """Compute average price from a list of offers."""
    prices = sorted(float(offer["price"]) for offer in offers if "price" in offer)
    prices = prices[: math.ceil(len(prices) / 2)]
    return sum(prices) / len(prices) if prices else 0.0


offers_database = json.load(Path("offers_database.json").open())
for card_name in offers_database:
    offers_database[card_name] = sorted(
        offers_database[card_name],
        key=lambda x: (-int(sellers_db_cards_available[str(x["seller"])]["cards_available"]), x["total_price"]),
    )
card_list = dict(
    sorted(
        card_list.items(),
        key=lambda x: (
            -x[1],  # most needed first
            -average_offer_price(offers_database[x[0]]),  # most expensive second
        ),
    )
)
for _ in range(100):
    offers_database = json.load(Path("offers_database.json").open())
    selected_offers = {}
    selected_sellers = set()
    items = list(card_list.items())
    random.shuffle(items)
    card_list = dict(items)
    for card_name, amount in card_list.items():
        if card_name not in offers_database:
            continue
        selected_offers[card_name] = []
        amount_left = amount
        while amount_left > 0:
            selected_offer = get_best_offer_use_selected_sellers(offers_database, card_name, amount_left)
            selected_offers[card_name].append(selected_offer)
            amount_left -= selected_offer["selected_amount"]

    json.dump(selected_offers, Path("algo4.json").open("w"), indent=2)
    total_price, items_price, shipping_price, sellers = calc_total_prices(selected_offers)
    print(f"Algo 4: {total_price=} {items_price=} {shipping_price=} {len(sellers)=}")


# ALGORITHM 5: Same as algorithm's 4 method but prioritizes sellers with the most amount of cards available.
#              If no offers with sellers that have been chosen, choose the cheapest (per card). Same as before.
#              If there are offers with sellers that have been chosen, choose the cheapest (per card) only from offers with sellers we've chosen.


def get_best_offer_biggest_sellers(
    offers_database: dict[str, list[dict[str, int | float | str]]], card_name: str, amount: int
):
    for offer in offers_database[card_name]:
        assert isinstance(offer["amount"], int)
        assert isinstance(offer["price"], float)
        assert isinstance(offer["shipping_price"], float)
        offer["selected_amount"] = offer["amount"] if amount >= offer["amount"] else amount
        assert isinstance(offer["selected_amount"], int)
        shipping_price = offer["shipping_price"] if offer["seller"] not in selected_sellers else 0.0
        offer["total_price_selected_amount"] = round(offer["price"] * offer["selected_amount"] + shipping_price, 2)
        assert isinstance(offer["total_price_selected_amount"], float)
        offer["price_per_card"] = round(offer["total_price_selected_amount"] / offer["selected_amount"], 2)
    offers_with_selected_sellers = sorted(
        (offer for offer in offers_database[card_name] if str(offer["seller"] in selected_sellers)),
        key=lambda x: x["price_per_card"],
    )
    if offers_with_selected_sellers:
        selected_offer = offers_with_selected_sellers[0]
        offers_database[card_name].pop(offers_database[card_name].index(selected_offer))
    else:
        offers_database[card_name] = sorted(offers_database[card_name], key=lambda x: x["price_per_card"])
        selected_offer = offers_database[card_name].pop(0)
    selected_sellers.add(str(selected_offer["seller"]))
    return selected_offer


offers_database = json.load(Path("offers_database.json").open())
for card_name in offers_database:
    offers_database[card_name] = sorted(
        offers_database[card_name],
        key=lambda x: (-int(sellers_db_cards_available[str(x["seller"])]["cards_available"]), x["total_price"]),
    )
selected_offers = {}
selected_sellers = set()
card_list = dict(
    sorted(
        card_list.items(),
        key=lambda x: (
            -x[1],  # most needed first
            -average_offer_price(offers_database[x[0]]),  # most expensive first
        ),
    )
)
for card_name, amount in card_list.items():
    if card_name not in offers_database:
        continue
    selected_offers[card_name] = []
    amount_left = amount
    while amount_left > 0:
        selected_offer = get_best_offer_use_selected_sellers(offers_database, card_name, amount_left)
        selected_offers[card_name].append(selected_offer)
        amount_left -= selected_offer["selected_amount"]

json.dump(selected_offers, Path("algo4.json").open("w"), indent=2)
total_price, items_price, shipping_price, sellers = calc_total_prices(selected_offers)
print(f"Algo 5: {total_price=} {items_price=} {shipping_price=} {len(sellers)=}")


# ALGORITHM 6: Prioritizes sellers with the most amount of cards available, over everything else.
#              Simply chooses the seller with the most amount every time.
#              Total disregard from price. If tied, chose the cheapest per card.


offers_database = json.load(Path("offers_database.json").open())
selected_offers = {}
# for card_name in offers_database:  # Sort first by total price in case sellers are tied on cards available.
#     offers_database[card_name] = sorted(offers_database[card_name], key=lambda x: x["total_price"])
for card_name, amount in card_list.items():
    if card_name not in offers_database:
        continue
    selected_offers[card_name] = []
    amount_left = amount
    for offer in sorted(
        offers_database[card_name],
        key=lambda x: (-int(sellers_db_cards_available[str(x["seller"])]["cards_available"]), x["total_price"]),
    ):
        assert isinstance(offer["amount"], int)
        if amount_left >= offer["amount"]:
            offer["selected_amount"] = offer["amount"]
            amount_left -= offer["amount"]
        else:
            offer["selected_amount"] = amount_left
            amount_left = 0
        selected_offers[card_name].append(offer)
        if amount_left <= 0:
            break

json.dump(selected_offers, Path("algo4.json").open("w"), indent=2)
total_price, items_price, shipping_price, sellers = calc_total_prices(selected_offers)
print(f"Algo 6: {total_price=} {items_price=} {shipping_price=} {len(sellers)=}")


# ALGORITHM 7: Prioritizes sellers with the most amount of cards available.
#              If no offers with sellers that have been chosen, choose the seller with the most amount.
#              If there are offers with sellers that have been chosen, choose the cheapest (per card) only from offers with sellers we've chosen.


def get_best_offer_biggest_sellers_all_in(
    offers_database: dict[str, list[dict[str, int | float | str]]], card_name: str, amount: int
):
    for offer in offers_database[card_name]:
        assert isinstance(offer["amount"], int)
        assert isinstance(offer["price"], float)
        assert isinstance(offer["shipping_price"], float)
        offer["selected_amount"] = offer["amount"] if amount >= offer["amount"] else amount
        assert isinstance(offer["selected_amount"], int)
        shipping_price = offer["shipping_price"] if offer["seller"] not in selected_sellers else 0.0
        offer["total_price_selected_amount"] = round(offer["price"] * offer["selected_amount"] + shipping_price, 2)
        assert isinstance(offer["total_price_selected_amount"], float)
        offer["price_per_card"] = round(offer["total_price_selected_amount"] / offer["selected_amount"], 2)
    offers_with_selected_sellers = sorted(
        (offer for offer in offers_database[card_name] if str(offer["seller"] in selected_sellers)),
        key=lambda x: x["price_per_card"],
    )
    if offers_with_selected_sellers:
        selected_offer = offers_with_selected_sellers[0]
        offers_database[card_name].pop(offers_database[card_name].index(selected_offer))
    else:
        offers_database[card_name] = sorted(
            offers_database[card_name],
            key=lambda x: (-int(sellers_db_cards_available[str(x["seller"])]["cards_available"]), x["price_per_card"]),
            reverse=True,
        )
        selected_offer = offers_database[card_name].pop(0)
    selected_sellers.add(str(selected_offer["seller"]))
    return selected_offer


offers_database = json.load(Path("offers_database.json").open())
for card_name in offers_database:
    offers_database[card_name] = sorted(
        offers_database[card_name],
        key=lambda x: (-int(sellers_db_cards_available[str(x["seller"])]["cards_available"]), x["total_price"]),
    )
selected_offers = {}
selected_sellers = set()
card_list = dict(
    sorted(
        card_list.items(),
        key=lambda x: (
            -x[1],  # most needed first
            -average_offer_price(offers_database[x[0]]),  # most expensive first
        ),
    )
)
for card_name, amount in card_list.items():
    if card_name not in offers_database:
        continue
    selected_offers[card_name] = []
    amount_left = amount
    while amount_left > 0:
        selected_offer = get_best_offer_biggest_sellers_all_in(offers_database, card_name, amount_left)
        selected_offers[card_name].append(selected_offer)
        amount_left -= selected_offer["selected_amount"]

json.dump(selected_offers, Path("algo4.json").open("w"), indent=2)
total_price, items_price, shipping_price, sellers = calc_total_prices(selected_offers)
print(f"Algo 7: {total_price=} {items_price=} {shipping_price=} {len(sellers)=}")
