import copy
import json
import re
import urllib.request
from pathlib import Path

import httpx
import requests

buy_considering = True
deck_ids: tuple[str | tuple[str, ...], ...] = (
    # PASTE MOXFIELD DECK IDS HERE
)
owned_deck_ids: tuple[str | tuple[str, ...], ...] = (
    # PASTE MOXFIELD DECK IDS HERE
)

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
    amount = match[1].strip()
    card_name = re.sub(r"(.*?[^/]) *//? *([^/].*)", r"\1 // \2", card_name).lower()
    purchased_cards[card_name] = purchased_cards.get(card_name, 0) + int(amount)

# json.dump(purchased_cards, Path("purchased.json").open("w"), indent=2, sort_keys=True)

# Get owned cards.
# Populate the owned.txt file. Format: amount of cards and card name.

owned_cards: dict[str, int] = {}
with Path("owned.txt").open() as f:
    lines = f.readlines()
for line in lines:
    line = line.strip()
    if not line:
        continue
    amount, card_name = line.split(" ", maxsplit=1)
    card_name = re.sub(r"(.*?[^/]) *//? *([^/].*)", r"\1 // \2", card_name).lower()
    owned_cards[card_name] = owned_cards.get(card_name, 0) + int(amount)

# json.dump(owned_cards, Path("owned.json").open("w"), indent=2, sort_keys=True)

# Calculate the cards that I have.

have = copy.copy(owned_cards)
for card_name, amount in purchased_cards.items():
    if card_name not in have:
        have[card_name] = amount
    else:
        have[card_name] += amount

# json.dump(have, Path("have.json").open("w"), indent=2, sort_keys=True)

# Get decks


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
        # with Path(deck_id + ".json").open("w") as fp:
        #     json.dump(data, fp, indent=2, sort_keys=True)
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
# decks: dict[str, dict[str, int]] = {}
for deck_id in deck_ids + owned_deck_ids:
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
        if deck_id in owned_deck_ids and card_name in have:
            if have[card_name] > amount:
                # I have more than I need for the deck, subtract from have and don't add to cards_in_deck because I don't need copies of this card for this deck.
                have[card_name] = have[card_name] - amount
            elif have[card_name] == amount:
                # I have the exact amount I need for the deck, remove card from have and don't add to cards_in_deck because I don't need copies of this card for this deck.
                have.pop(card_name)
            else:
                # I don't have enough copies, remove card from have and add to cards_in_deck the amount minus what I have (what I actually need).
                cards_in_decks[card_name] = cards_in_decks.get(card_name, 0) + amount - have[card_name]
                have.pop(card_name)
        else:
            cards_in_decks[card_name] = cards_in_decks.get(card_name, 0) + amount
        # decks[str(deck_id)][card_name] = decks.get(str(deck_id), {}).get(card_name, 0) + amount
    for card_name, amount in maybeboard.items():
        if deck_id in owned_deck_ids and card_name in have:
            if amount > have[card_name]:
                # I don't have enough copies, remove card from have and add to cards_in_deck the amount minus what I have (what I actually need).
                considering_cards[card_name] = considering_cards.get(card_name, 0) + amount - have[card_name]
            # else: simply don't add to considering, this way the card will not be taken into account, since we already have it
            #       this helps to not pollute the 'avoided' list
        else:
            considering_cards[card_name] = considering_cards.get(card_name, 0) + amount


# json.dump(cards_in_decks, Path("in_decks.json").open("w"), indent=2, sort_keys=True)
# json.dump(considering_cards, Path("considering.json").open("w"), indent=2, sort_keys=True)

# Calculate the cards that I need.

need = copy.copy(cards_in_decks)
need_decks = copy.copy(cards_in_decks)
need_considering = {}
if buy_considering:
    for card_name, amount in considering_cards.items():
        if card_name not in need:
            # Only add 1 copy of each card from considering and only if it is not already in the decks.
            need[card_name] = 1
            need_considering[card_name] = 1

# json.dump(need, Path("need.json").open("w"), indent=2, sort_keys=True)
# json.dump(need_decks, Path("need_decks.json").open("w"), indent=2, sort_keys=True)
# json.dump(need_considering, Path("need_considering.json").open("w"), indent=2, sort_keys=True)

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

json.dump(avoided, Path("avoided.json").open("w"), indent=2, sort_keys=True)
# json.dump(avoided_owned, Path("avoided_owned.json").open("w"), indent=2, sort_keys=True)
# json.dump(avoided_purchased, Path("avoided_purchased.json").open("w"), indent=2, sort_keys=True)

with Path("to_purchase.txt").open("w") as f:
    for card_name, amount in sorted(to_purchase.items()):
        f.write(f"{amount} {card_name}\n")

to_purchase_decks = {}
for card_name, amount in need_decks.items():
    if card_name not in have:
        to_purchase_decks[card_name] = amount
    else:
        if have[card_name] < amount:
            to_purchase_decks[card_name] = amount - have[card_name]

with Path("to_purchase_decks.txt").open("w") as f:
    for card_name, amount in sorted(to_purchase_decks.items()):
        f.write(f"{amount} {card_name}\n")

to_purchase_considering = {}
for card_name, amount in need_considering.items():
    if card_name not in have:
        to_purchase_considering[card_name] = amount
    else:
        if have[card_name] < amount:
            to_purchase_considering[card_name] = amount - have[card_name]

with Path("to_purchase_considering.txt").open("w") as f:
    for card_name, amount in sorted(to_purchase_considering.items()):
        f.write(f"{amount} {card_name}\n")
