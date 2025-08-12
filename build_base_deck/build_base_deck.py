import json
from pathlib import Path

import pyedhrec

commander_name = "Anim Pakal, Thousandth Moon"
vendor = "cardkingdom"
synergy_threshold = 0.15
inclusion_threshold = 0.25
price_threshold = 10

edhrec = pyedhrec.EDHRec()

cards = {}
data = edhrec.get_commander_data(commander_name)
for card_list in data["container"]["json_dict"]["cardlists"]:
    for card in card_list["cardviews"]:
        if card["synergy"] >= synergy_threshold or card["num_decks"] / card["potential_decks"] >= inclusion_threshold:
            cards[card["name"]] = card

cards_budget = {}
data = edhrec.get_commander_data(commander_name, "budget")
for card_list in data["container"]["json_dict"]["cardlists"]:
    for card in card_list["cardviews"]:
        if card["synergy"] >= synergy_threshold or card["num_decks"] / card["potential_decks"] >= inclusion_threshold:
            cards_budget[card["name"]] = card

data = edhrec.get_card_list([card_name for card_name in cards])
for card in data["cards"].values():
    if card["prices"][vendor]["price"] <= price_threshold:
        cards[card["name"]]["price"] = card["prices"][vendor]["price"]
    else:
        cards.pop(card["name"])

data = edhrec.get_card_list([card_name for card_name in cards_budget])
for card in data["cards"].values():
    if card["prices"][vendor]["price"] <= price_threshold:
        cards_budget[card["name"]]["price"] = card["prices"][vendor]["price"]
    else:
        cards_budget.pop(card["name"])


with Path("cards.json").open("w") as fp:
    json.dump(cards, fp, indent=2, sort_keys=True)

with Path("cards_budget.json").open("w") as fp:
    json.dump(cards_budget, fp, indent=2, sort_keys=True)


avg_deck = []
data = edhrec.get_commanders_average_deck(commander_name)
for card in data["decklist"]:
    avg_deck.append(card.split(" ", maxsplit=1)[1])

avg_deck_budget = []
data = edhrec.get_commanders_average_deck(commander_name, "budget")
for card in data["decklist"]:
    avg_deck_budget.append(card.split(" ", maxsplit=1)[1])

data = edhrec.get_card_list(avg_deck)
for card in data["cards"].values():
    if card["prices"][vendor]["price"] > price_threshold:
        avg_deck.remove(card["name"])

data = edhrec.get_card_list(avg_deck_budget)
for card in data["cards"].values():
    if card["prices"][vendor]["price"] > price_threshold:
        avg_deck_budget.remove(card["name"])


with Path("avg_deck.json").open("w") as fp:
    json.dump(avg_deck, fp, indent=2, sort_keys=True)

with Path("avg_deck_budget.json").open("w") as fp:
    json.dump(avg_deck_budget, fp, indent=2, sort_keys=True)


cards_occurrences: dict[str, int] = {}
for card_name in cards:
    cards_occurrences[card_name] = cards_occurrences.get(card_name, 0) + 1
for card_name in cards_budget:
    cards_occurrences[card_name] = cards_occurrences.get(card_name, 0) + 1
for card_name in avg_deck:
    cards_occurrences[card_name] = cards_occurrences.get(card_name, 0) + 1
for card_name in avg_deck_budget:
    cards_occurrences[card_name] = cards_occurrences.get(card_name, 0) + 1
cards_occurrences.pop(commander_name)

cards_main_deck = [card_name for card_name, occurrences in cards_occurrences.items() if occurrences >= 3]
cards_considering = [card_name for card_name, occurrences in cards_occurrences.items() if occurrences <= 2]


print("MAIN DECK:\n")
for card_name in sorted(cards_main_deck):
    print(card_name)

print()

print("CONSIDERING:\n")
for card_name in sorted(cards_considering):
    print(card_name)
