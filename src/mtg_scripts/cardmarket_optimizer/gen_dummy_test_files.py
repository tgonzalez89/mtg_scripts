import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict


class OfferRecord(TypedDict):
    total_price: float
    price: float
    shipping_price: float
    amount: int
    seller: str


MAX_GENERATED_VALUE: Final = 1000


@dataclass(frozen=True)
class GenerationConfig:
    """Parameters used to generate Cardmarket optimizer fixtures."""

    num_sellers: int
    seller_min_shipping_price: float
    seller_max_shipping_price: float
    offer_min_price: float
    offer_max_price: float
    offer_min_amount: int
    offer_max_amount: int
    num_cards: int
    card_min_offers: int
    card_max_offers: int
    buy_list_min_card_amount: int
    buy_list_max_card_amount: int
    card_list_path: str
    sellers_database_path: str
    offers_database_path: str


def generate_data(config: GenerationConfig) -> None:
    """Generate Cardmarket optimizer fixture files."""
    # Validate input ranges
    ranges = (
        0 < config.seller_min_shipping_price <= config.seller_max_shipping_price <= MAX_GENERATED_VALUE,
        0 < config.offer_min_price <= config.offer_max_price <= MAX_GENERATED_VALUE,
        1 <= config.offer_min_amount <= config.offer_max_amount <= MAX_GENERATED_VALUE,
        1 <= config.card_min_offers <= config.card_max_offers <= MAX_GENERATED_VALUE,
        1 <= config.buy_list_min_card_amount <= config.buy_list_max_card_amount <= MAX_GENERATED_VALUE,
    )
    if not all(ranges):
        message = "Generated data ranges are invalid."
        raise ValueError(message)

    # Generate sellers_db
    sellers_db: dict[str, float] = {
        f"seller{i + 1}": round(random.uniform(config.seller_min_shipping_price, config.seller_max_shipping_price), 2)
        for i in range(config.num_sellers)
    }

    with Path(config.sellers_database_path).open("w", encoding="utf-8") as f:
        json.dump(sellers_db, f, indent=2, sort_keys=True)

    # Generate offers_db
    offers_db: dict[str, list[OfferRecord]] = {}
    buy_list: dict[str, int] = {}

    for card_index in range(1, config.num_cards + 1):
        card_name = f"card-name-{card_index}"
        num_offers = random.randint(config.card_min_offers, config.card_max_offers)
        offers: list[OfferRecord] = []
        for _ in range(num_offers):
            seller = random.choice(list(sellers_db.keys()))
            shipping_price = sellers_db[seller]
            price = round(random.uniform(config.offer_min_price, config.offer_max_price), 2)
            amount = random.randint(config.offer_min_amount, config.offer_max_amount)
            total_price = round(price + shipping_price, 2)
            offer: OfferRecord = {
                "total_price": total_price,
                "price": price,
                "shipping_price": shipping_price,
                "amount": amount,
                "seller": seller,
            }
            offers.append(offer)
        offers_db[card_name] = offers

        card_amount = random.randint(config.buy_list_min_card_amount, config.buy_list_max_card_amount)
        buy_list[card_name] = card_amount

    with Path(config.offers_database_path).open("w", encoding="utf-8") as f:
        json.dump(offers_db, f, indent=2, sort_keys=True)

    with Path(config.card_list_path).open("w", encoding="utf-8") as f:
        f.writelines(f"{amount} {card_name}\n" for card_name, amount in buy_list.items())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-sellers", type=int, required=True)
    parser.add_argument("--seller-min-shipping-price", type=float, required=True)
    parser.add_argument("--seller-max-shipping-price", type=float, required=True)
    parser.add_argument("--offer-min-price", type=float, required=True)
    parser.add_argument("--offer-max-price", type=float, required=True)
    parser.add_argument("--offer-min-amount", type=int, required=True)
    parser.add_argument("--offer-max-amount", type=int, required=True)
    parser.add_argument("--num-cards", type=int, required=True)
    parser.add_argument("--card-min-offers", type=int, required=True)
    parser.add_argument("--card-max-offers", type=int, required=True)
    parser.add_argument("--buy-list-min-card-amount", type=int, required=True)
    parser.add_argument("--buy-list-max-card-amount", type=int, required=True)
    parser.add_argument(
        "--card-list",
        "-c",
        default="card_list.txt",
        help="Path to output text file containing the card list (default card_list.txt).",
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

    args = parser.parse_args()

    generate_data(
        GenerationConfig(
            num_sellers=args.num_sellers,
            seller_min_shipping_price=args.seller_min_shipping_price,
            seller_max_shipping_price=args.seller_max_shipping_price,
            offer_min_price=args.offer_min_price,
            offer_max_price=args.offer_max_price,
            offer_min_amount=args.offer_min_amount,
            offer_max_amount=args.offer_max_amount,
            num_cards=args.num_cards,
            card_min_offers=args.card_min_offers,
            card_max_offers=args.card_max_offers,
            buy_list_min_card_amount=args.buy_list_min_card_amount,
            buy_list_max_card_amount=args.buy_list_max_card_amount,
            card_list_path=args.card_list,
            sellers_database_path=args.sellers_database,
            offers_database_path=args.offers_database,
        )
    )
