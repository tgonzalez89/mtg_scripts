import argparse
import json
import random


def generate_data(
    num_sellers,
    seller_min_shipping_price,
    seller_max_shipping_price,
    offer_min_price,
    offer_max_price,
    offer_min_amount,
    offer_max_amount,
    num_cards,
    card_min_offers,
    card_max_offers,
    buy_list_min_card_amount,
    buy_list_max_card_amount,
):
    # Validate input ranges
    assert 0 < seller_min_shipping_price <= seller_max_shipping_price <= 1000
    assert 0 < offer_min_price <= offer_max_price <= 1000
    assert 1 <= offer_min_amount <= offer_max_amount <= 1000
    assert 1 <= card_min_offers <= card_max_offers <= 1000
    assert 1 <= buy_list_min_card_amount <= buy_list_max_card_amount <= 1000

    # Generate sellers_db
    sellers_db = {
        f"seller{i + 1}": round(random.uniform(seller_min_shipping_price, seller_max_shipping_price), 2)
        for i in range(num_sellers)
    }

    with open("sellers_database.json", "w") as f:
        json.dump(sellers_db, f, indent=2, sort_keys=True)

    # Generate offers_db
    offers_db = {}
    buy_list = {}

    for card_index in range(1, num_cards + 1):
        card_name = f"card-name-{card_index}"
        num_offers = random.randint(card_min_offers, card_max_offers)
        offers = []
        for _ in range(num_offers):
            seller = random.choice(list(sellers_db.keys()))
            shipping_price = sellers_db[seller]
            price = round(random.uniform(offer_min_price, offer_max_price), 2)
            amount = random.randint(offer_min_amount, offer_max_amount)
            total_price = round(price + shipping_price, 2)
            offer = {
                "total_price": total_price,
                "price": price,
                "shipping_price": shipping_price,
                "amount": amount,
                "seller": seller,
            }
            offers.append(offer)
        offers_db[card_name] = offers

        card_amount = random.randint(buy_list_min_card_amount, buy_list_max_card_amount)
        buy_list[card_name] = card_amount

    with open("offers_database.json", "w") as f:
        json.dump(offers_db, f, indent=2, sort_keys=True)

    with open("card_list.txt", "w") as f:
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

    args = parser.parse_args()

    generate_data(
        args.num_sellers,
        args.seller_min_shipping_price,
        args.seller_max_shipping_price,
        args.offer_min_price,
        args.offer_max_price,
        args.offer_min_amount,
        args.offer_max_amount,
        args.num_cards,
        args.card_min_offers,
        args.card_max_offers,
        args.buy_list_min_card_amount,
        args.buy_list_max_card_amount,
    )
