import json


def extract_seller_shipping(data: dict) -> dict:
    """
    Extracts a mapping of seller: shipping_price from a nested JSON structure.

    Args:
        data (dict): JSON object with card info, e.g. { "Card Name": { "Set": { ... } } }

    Returns:
        dict: { seller_name: shipping_price, ... }
    """
    seller_shipping = {}

    for card_name, sets in data.items():
        for set_name, details in sets.items():
            offers = details.get("offers", [])
            for offer in offers:
                seller = offer.get("seller")
                shipping_price = offer.get("shipping_price")
                if seller is not None and shipping_price is not None:
                    seller_shipping[seller] = shipping_price

    return seller_shipping


def build_seller_database(input_path="offers_database_by_edition.json", output_path="sellers_database.json"):
    """
    Reads offer data, extracts seller shipping info, and writes to a new JSON file.
    """
    # Step 1: Read input JSON
    with open(input_path, "r") as infile:
        offers_data = json.load(infile)

    # Step 2: Extract seller data
    sellers_data = extract_seller_shipping(offers_data)

    # Step 3: Write output JSON
    with open(output_path, "w") as outfile:
        json.dump(sellers_data, outfile, indent=2, ensure_ascii=False)

    print(f"✅ Seller data extracted and saved to '{output_path}'")


if __name__ == "__main__":
    build_seller_database()
