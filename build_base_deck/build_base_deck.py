import json
from pathlib import Path

import pyedhrec

commander_name = "PASTE COMMANDER NAME HERE"
vendor = "cardkingdom"
synergy_threshold = 0.15
inclusion_threshold = 0.15
price_threshold = 20
themes = (None,)  # Add themes here


# Modified EDHRec class to support budget and themes.
class MyEDHRec(pyedhrec.EDHRec):
    @pyedhrec.caching.commander_cache
    def get_commander_data(self, card_name: str, budget: str | None = None, theme: str | None = None) -> dict:
        commander_uri, params = self._build_nextjs_uri("commanders", card_name, theme=theme, budget=budget)
        res = self._get(commander_uri, query_params=params)
        data = self._get_nextjs_data(res)
        return data

    @pyedhrec.caching.average_deck_cache
    def get_commanders_average_deck(self, card_name: str, budget: str | None = None, theme: str | None = None) -> dict:
        average_deck_uri, params = self._build_nextjs_uri("average-decks", card_name, theme=theme, budget=budget)
        res = self._get(average_deck_uri, query_params=params)
        data = self._get_nextjs_data(res)
        deck_obj = {"commander": card_name, "decklist": data.get("deck")}
        return deck_obj


edhrec = MyEDHRec()
cards_occurrences: dict[str, int] = {}

for theme in themes:
    print(f"Theme: {theme}")
    cards = {}
    data = edhrec.get_commander_data(commander_name, None, theme)
    for card_list in data["container"]["json_dict"]["cardlists"]:
        for card in card_list["cardviews"]:
            if (
                card["synergy"] >= synergy_threshold
                or card["num_decks"] / card["potential_decks"] >= inclusion_threshold
            ):
                cards[card["name"]] = card

    cards_budget = {}
    data = edhrec.get_commander_data(commander_name, "budget", theme)
    for card_list in data["container"]["json_dict"]["cardlists"]:
        for card in card_list["cardviews"]:
            if (
                card["synergy"] >= synergy_threshold
                or card["num_decks"] / card["potential_decks"] >= inclusion_threshold
            ):
                cards_budget[card["name"]] = card

    # Filter by price
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

    with Path(f"cards_{theme}.json").open("w") as fp:
        json.dump(cards, fp, indent=2, sort_keys=True)

    with Path(f"cards_budget_{theme}.json").open("w") as fp:
        json.dump(cards_budget, fp, indent=2, sort_keys=True)

    avg_deck = []
    data = edhrec.get_commanders_average_deck(commander_name, None, theme)
    for card in data["decklist"]:
        avg_deck.append(card.split(" ", maxsplit=1)[1])

    avg_deck_budget = []
    data = edhrec.get_commanders_average_deck(commander_name, "budget", theme)
    for card in data["decklist"]:
        avg_deck_budget.append(card.split(" ", maxsplit=1)[1])

    # Filter by price
    data = edhrec.get_card_list(avg_deck)
    for card in data["cards"].values():
        if card["prices"][vendor]["price"] > price_threshold:
            avg_deck.remove(card["name"])

    data = edhrec.get_card_list(avg_deck_budget)
    for card in data["cards"].values():
        if card["prices"][vendor]["price"] > price_threshold:
            avg_deck_budget.remove(card["name"])

    with Path(f"avg_deck_{theme}.json").open("w") as fp:
        json.dump(avg_deck, fp, indent=2, sort_keys=True)

    with Path(f"avg_deck_budget_{theme}.json").open("w") as fp:
        json.dump(avg_deck_budget, fp, indent=2, sort_keys=True)

    for card_name in cards:
        cards_occurrences[card_name] = cards_occurrences.get(card_name, 0) + 1
    for card_name in cards_budget:
        cards_occurrences[card_name] = cards_occurrences.get(card_name, 0) + 1
    for card_name in avg_deck:
        cards_occurrences[card_name] = cards_occurrences.get(card_name, 0) + 1
    for card_name in avg_deck_budget:
        cards_occurrences[card_name] = cards_occurrences.get(card_name, 0) + 1
    cards_occurrences.pop(commander_name)

cards_main_deck = [card_name for card_name, occurrences in cards_occurrences.items() if occurrences >= 3 * len(themes)]
cards_considering = [
    card_name for card_name, occurrences in cards_occurrences.items() if occurrences <= 2 * len(themes)
]


print("MAIN DECK:\n")
for card_name in sorted(cards_main_deck):
    print(card_name)

print()

print("CONSIDERING:\n")
for card_name in sorted(cards_considering):
    print(card_name)
