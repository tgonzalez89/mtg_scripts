"""Pure offer selection and seller accounting for the Cardmarket optimizer."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .models import SelectedOfferRecord, SellerAvailability


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
    """Compute the lower-half trimmed average for one offer field."""
    prices = sorted(float(cast("str | float | int", dict(offer)[key])) for offer in offers if key in offer)
    prices = prices[: math.ceil(len(prices) / 2)]
    return round(sum(prices) / len(prices), 2) if prices else 0.0


def get_best_offer(
    offers: list[SelectedOfferRecord],
    amount: int,
    selected_sellers: set[str],
    seller_availability: dict[str, SellerAvailability],
) -> SelectedOfferRecord | None:
    # Selection fields are intentionally written to and the chosen record removed from this working copy.
    for offer in offers:
        selected_amount = min(int(offer["amount"]), amount)
        offer["selected_amount"] = selected_amount
        shipping_price = float(offer["shipping_price"]) if offer["seller"] not in selected_sellers else 0.0
        total_price = round(float(offer["price"]) * selected_amount + shipping_price, 2)
        offer["price_per_card"] = round(total_price / selected_amount, 2)
    offers.sort(
        key=lambda offer: (
            offer["price_per_card"],
            -int(seller_availability[str(offer["seller"])]["cards_available"]),
        )
    )
    selected_offer = offers.pop(0)
    selected_sellers.add(str(selected_offer["seller"]))
    return selected_offer


def run_algo(
    card_list: dict[str, int],
    offers_database: dict[str, list[SelectedOfferRecord]],
    seller_availability: dict[str, SellerAvailability],
    selected_offers: dict[str, list[SelectedOfferRecord]] | None = None,
    selected_sellers: set[str] | None = None,
) -> tuple[dict[str, list[SelectedOfferRecord]], set[str]]:
    ordered_cards = dict(
        sorted(
            card_list.items(),
            key=lambda item: (
                len(offers_database[item[0]]),
                -item[1],
                -average_offer_by_key(offers_database[item[0]], "price"),
            ),
        )
    )

    if selected_offers is None:
        selected_offers = {}
    if selected_sellers is None:
        selected_sellers = set()
    for card_name, amount in ordered_cards.items():
        if card_name not in offers_database:
            continue
        selected_offers[card_name] = []
        amount_left = amount
        while amount_left > 0:
            selected_offer = get_best_offer(
                offers_database[card_name], amount_left, selected_sellers, seller_availability
            )
            if selected_offer is None:
                break
            selected_offers[card_name].append(selected_offer)
            amount_left -= int(selected_offer["selected_amount"])
    return selected_offers, selected_sellers


def build_seller_availability(
    card_list: dict[str, int],
    offers_database: dict[str, list[SelectedOfferRecord]],
    sellers_database: dict[str, float],
) -> dict[str, SellerAvailability]:
    availability: dict[str, SellerAvailability] = {
        seller: {"shipping_price": shipping_price, "cards_available": 0}
        for seller, shipping_price in sellers_database.items()
    }
    for card_name, amount in card_list.items():
        if card_name not in offers_database:
            continue
        for offer in offers_database[card_name]:
            seller = str(offer["seller"])
            if seller not in availability:
                availability[seller] = {"shipping_price": float(offer["shipping_price"]), "cards_available": 0}
            availability[seller]["cards_available"] += min(int(offer["amount"]), amount)
    return availability


def extract_single_card_sellers(
    selected_offers: dict[str, list[SelectedOfferRecord]], selected_sellers: set[str]
) -> dict[str, int]:
    offers_by_seller: dict[str, list[SelectedOfferRecord]] = {}
    for card_name, offers in selected_offers.items():
        for offer in offers:
            offer["card_name"] = card_name
            seller = str(offer["seller"])
            offers_by_seller.setdefault(seller, []).append(offer)

    new_card_list: dict[str, int] = {}
    for seller, seller_offers in offers_by_seller.items():
        if sum(int(offer["selected_amount"]) for offer in seller_offers) != 1:
            continue
        selected_sellers.remove(seller)
        new_card_list[str(seller_offers[0]["card_name"])] = 1
        for card_name, offers in tuple(selected_offers.items()):
            for index, offer in enumerate(offers):
                if seller_offers[0] == offer:
                    offers.pop(index)
                    if not offers:
                        selected_offers.pop(card_name)
                    break
    return new_card_list
