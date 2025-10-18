import argparse
import json
from pathlib import Path

import pyedhrec

VERBOSE = True  # Set to True to enable info messages
DEBUG_JSON = False  # Set to True to enable saving intermediate data as json files


def parse_args():
    parser = argparse.ArgumentParser()

    # Required positional or optional commander names
    parser.add_argument(
        "--commander-names", "-c", nargs="+", required=True, help="List of commander names (at least one required)."
    )

    parser.add_argument("--themes", "-t", nargs="*", default=[None], help="List of themes (optional).")

    parser.add_argument(
        "--synergy-threshold", "-s", type=float, default=0.15, help="Synergy threshold between 0 and 1 (default: 0.15)."
    )

    parser.add_argument(
        "--inclusion-threshold",
        "-i",
        type=float,
        default=0.15,
        help="Inclusion threshold between 0 and 1 (default: 0.15).",
    )

    parser.add_argument(
        "--price-threshold", "-p", type=float, default=25.0, help="Price threshold (positive float, default: 25)."
    )

    parser.add_argument(
        "--vendor",
        "-v",
        choices=[
            "cardhoarder",
            "cardkingdom",
            "cardmarket",
            "face2face",
            "manapool",
            "mtgstocks",
            "scg",
            "tcgl",
            "tcgplayer",
        ],
        default="cardkingdom",
        help="Vendor to use (default: cardkingdom).",
    )

    args = parser.parse_args()

    # Convert lists to tuples for consistency
    args.commander_names = tuple(args.commander_names)
    args.themes = tuple(args.themes) if args.themes else (None,)

    if not (args.synergy_threshold >= 0 and args.synergy_threshold <= 1):
        raise argparse.ArgumentTypeError("Must be between 0 and 1.")

    if not (args.inclusion_threshold >= 0 and args.inclusion_threshold <= 1):
        raise argparse.ArgumentTypeError("Must be between 0 and 1.")

    if not (args.price_threshold >= 0):
        raise argparse.ArgumentTypeError("Must be >= 0.")

    return args


args = parse_args()


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

for commander_name in args.commander_names:
    if VERBOSE:
        print(f"Processing commander: {commander_name}")
    for theme in args.themes:
        if VERBOSE:
            print(f"Processing theme: {theme}")
        cards = {}
        data = edhrec.get_commander_data(commander_name, None, theme)
        for card_list in data["container"]["json_dict"]["cardlists"]:
            for card in card_list["cardviews"]:
                if (
                    card["synergy"] >= args.synergy_threshold
                    or card["num_decks"] / card["potential_decks"] >= args.inclusion_threshold
                ):
                    cards[card["name"]] = card

        cards_budget = {}
        data = edhrec.get_commander_data(commander_name, "budget", theme)
        for card_list in data["container"]["json_dict"]["cardlists"]:
            for card in card_list["cardviews"]:
                if (
                    card["synergy"] >= args.synergy_threshold
                    or card["num_decks"] / card["potential_decks"] >= args.inclusion_threshold
                ):
                    cards_budget[card["name"]] = card

        # Filter by price
        data = edhrec.get_card_list([card_name for card_name in cards])
        for card in data["cards"].values():
            if card["prices"][args.vendor]["price"] <= args.price_threshold:
                cards[card["name"]]["price"] = card["prices"][args.vendor]["price"]
            else:
                cards.pop(card["name"])

        data = edhrec.get_card_list([card_name for card_name in cards_budget])
        for card in data["cards"].values():
            if card["prices"][args.vendor]["price"] <= args.price_threshold:
                cards_budget[card["name"]]["price"] = card["prices"][args.vendor]["price"]
            else:
                cards_budget.pop(card["name"])

        if DEBUG_JSON:
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
            if card["prices"][args.vendor]["price"] > args.price_threshold:
                avg_deck.remove(card["name"])

        data = edhrec.get_card_list(avg_deck_budget)
        for card in data["cards"].values():
            if card["prices"][args.vendor]["price"] > args.price_threshold:
                avg_deck_budget.remove(card["name"])

        if DEBUG_JSON:
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

cards_main_deck = [
    card_name
    for card_name, occurrences in cards_occurrences.items()
    if occurrences >= 3 * len(args.themes) * len(args.commander_names)
]
cards_considering = [
    card_name
    for card_name, occurrences in cards_occurrences.items()
    if occurrences <= 2 * len(args.themes) * len(args.commander_names)
]

with Path("main_deck.txt").open("w") as fp:
    fp.writelines(card_name + "\n" for card_name in sorted(cards_main_deck))

with Path("considering.txt").open("w") as fp:
    fp.writelines(card_name + "\n" for card_name in sorted(cards_considering))
