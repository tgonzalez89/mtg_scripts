import copy
import json
import re
import urllib.request
from pathlib import Path

import httpx
import requests

buy_considering = True
deck_ids = ("ey9UzE4YJEGX7jzS_Rr0pA", "LtNWOzHmEUittPxGYZUFxw", ("6kH8ejb2tkuN4E0ifJ_PAw", "IoAKn_wfLECpyorKx52ZvQ"))
# deck_ids = ("ey9UzE4YJEGX7jzS_Rr0pA", "LtNWOzHmEUittPxGYZUFxw")
# deck_ids = (("6kH8ejb2tkuN4E0ifJ_PAw", "IoAKn_wfLECpyorKx52ZvQ"),)


# Get purchased cards.
# Populate the purchased.txt file.
#   1. Open https://www.cardtrader.com/orders/buyer_future_order
#   2. Copy-paste the list of cards into into purchased.txt.

purchased_cards: dict[str, int] = {}
with Path("purchased.txt").open() as f:
    text = f.read()
pattern = re.compile(r"(.+?)\n\t\n\w+ (\d+)\n\t\1", re.DOTALL)
matches = pattern.findall(text)
for match in matches:
    card_name = match[0].strip()
    number = match[1].strip()
    card_name = re.sub(r"(.*?[^/]) *//? *([^/].*)", r"\1 // \2", card_name).lower()
    purchased_cards[card_name] = purchased_cards.get(card_name, 0) + int(number)

json.dump(purchased_cards, Path("purchased.json").open("w"), indent=2, sort_keys=True)

# Get owned cards.
# Populate the owned.txt file. Format: number of cards and card name.

owned_cards: dict[str, int] = {}
with Path("owned.txt").open() as f:
    lines = f.readlines()
for line in lines:
    line = line.strip()
    if not line:
        continue
    number, card_name = line.split(" ", maxsplit=1)
    card_name = re.sub(r"(.*?[^/]) *//? *([^/].*)", r"\1 // \2", card_name).lower()
    owned_cards[card_name] = owned_cards.get(card_name, 0) + int(number)

json.dump(owned_cards, Path("owned.json").open("w"), indent=2, sort_keys=True)

# Get the required cards for each deck.
# Populate the deck.txt files.
#   1. Open the deck in Moxfield.
#   2. Click on More > Export > Copy for Moxfield.
#   3. Paste the contents into a text file and save it as deck.txt.
#   4. The file should now contain the number of cards, the card name, the set id in parenthesis and the card id within the set.

# decks: dict[str, int] = {}
# for deck_file in Path(".").glob("*/deck.txt"):
#     with deck_file.open() as f:
#         lines = f.readlines()
#     for line in lines:
#         line = line.strip()
#         if not line:
#             continue
#         number_and_card_name, _ = line.split(" (", maxsplit=1)
#         number, card_name = number_and_card_name.split(" ", maxsplit=1)
#         card_name = re.sub(r"(.*?[^/]) *//? *([^/].*)", r"\1 // \2", card_name).lower()
#         decks[card_name] = decks.get(card_name, 0) + int(number)

# json.dump(decks, Path("decks.json").open("w"), indent=2, sort_keys=True)

# Get the required cards in the considering category.
# Populate the considering.txt file.
#   1. Open the deck in Moxfield.
#   2. Click on Bulk Edit > Considering and copy the contents.
#   3. Paste the contents into a text file and save it as considering.txt.
#   4. The file should now contain the number of cards, the card name, the set id in parenthesis, the card id within the set and the tags.

# considering: dict[str, int] = {}
# for deck_file in Path(".").glob("*/considering.txt"):
#     with deck_file.open() as f:
#         lines = f.readlines()
#     for line in lines:
#         line = line.strip()
#         if not line:
#             continue
#         number_and_card_name, _ = line.split(" (", maxsplit=1)
#         number, card_name = number_and_card_name.split(" ", maxsplit=1)
#         card_name = re.sub(r"(.*?[^/]) *//? *([^/].*)", r"\1 // \2", card_name).lower()
#         considering[card_name] = considering.get(card_name, 0) + int(number)

# json.dump(considering, Path("considering.json").open("w"), indent=2, sort_keys=True)


def download_deck(deck_id) -> tuple[dict[str, int], dict[str, int]]:
    moxfield_url = "https://www.moxfield.com/decks/"
    moxfield_api_url = "https://api.moxfield.com/v2/decks/all/"
    headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"}
    request = urllib.request.Request(moxfield_api_url + deck_id, headers=headers)
    with urllib.request.urlopen(request) as response:
        if response.status != 200:
            print(f"Failed to get data using urllib. Status code: {response.status_code}")
            exit()
        encoding = response.headers.get_content_charset("utf-8")
        data = json.loads(response.read().decode(encoding))
        with Path(deck_id + ".json").open("w") as fp:
            json.dump(data, fp, indent=2, sort_keys=True)
    if False:
        with httpx.Client(headers=headers) as http_client:
            response = http_client.head(moxfield_url + deck_id)
            response = http_client.get(moxfield_api_url + deck_id)
            if response.status_code != 200:
                print(f"Failed to get data using httpx. Status code: {response.status_code}")
                exit()
            data = response.json()
            print("DATA httpx")
        response = requests.get(moxfield_api_url + deck_id, headers=headers)
        if response.status_code != 200:
            print(f"Failed to get data using requests. Status code: {response.status_code}")
            exit()
        data = response.json()
        print("DATA requests")
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
for deck_id in deck_ids:
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
        cards_in_decks[card_name] = cards_in_decks.get(card_name, 0) + amount
    for card_name, amount in maybeboard.items():
        considering_cards[card_name] = considering_cards.get(card_name, 0) + amount


json.dump(cards_in_decks, Path("in_decks.json").open("w"), indent=2, sort_keys=True)
json.dump(considering_cards, Path("considering.json").open("w"), indent=2, sort_keys=True)

# Calculate the cards that I have.

have = copy.copy(owned_cards)
for card_name, number in purchased_cards.items():
    if card_name not in have:
        have[card_name] = number
    else:
        have[card_name] += number

json.dump(have, Path("have.json").open("w"), indent=2, sort_keys=True)

# Calculate the cards that I need.

need_all = copy.copy(cards_in_decks)
need_decks = copy.copy(cards_in_decks)
need_considering = {}
if buy_considering:
    for card_name, number in considering_cards.items():
        if card_name not in need_all:
            # Only add 1 copy of each card from considering and only if it is not already in the decks.
            need_all[card_name] = 1
            need_considering[card_name] = 1

json.dump(need_all, Path("need_all.json").open("w"), indent=2, sort_keys=True)

# Calculate the cards that I need to buy.

to_purchase = {}
for card_name, number in need_all.items():
    if card_name not in have:
        to_purchase[card_name] = number
    else:
        if have[card_name] < number:
            to_purchase[card_name] = number - have[card_name]

with Path("to_purchase.txt").open("w") as f:
    for card_name, number in sorted(to_purchase.items()):
        f.write(f"{number} {card_name}\n")

json.dump(to_purchase, Path("to_purchase.json").open("w"), indent=2, sort_keys=True)

to_purchase_decks = {}
for card_name, number in need_decks.items():
    if card_name not in have:
        to_purchase_decks[card_name] = number
    else:
        if have[card_name] < number:
            to_purchase_decks[card_name] = number - have[card_name]

with Path("to_purchase_decks.txt").open("w") as f:
    for card_name, number in sorted(to_purchase_decks.items()):
        f.write(f"{number} {card_name}\n")

json.dump(to_purchase_decks, Path("to_purchase_decks.json").open("w"), indent=2, sort_keys=True)

to_purchase_considering = {}
for card_name, number in need_considering.items():
    if card_name not in have:
        to_purchase_considering[card_name] = number
    else:
        if have[card_name] < number:
            to_purchase_considering[card_name] = number - have[card_name]

with Path("to_purchase_considering.txt").open("w") as f:
    for card_name, number in sorted(to_purchase_considering.items()):
        f.write(f"{number} {card_name}\n")

json.dump(to_purchase_considering, Path("to_purchase_considering.json").open("w"), indent=2, sort_keys=True)
