from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

import argparse
import json
from pathlib import Path
from typing import Final

from . import deck_builder, edhrec_client

VERBOSE: Final[bool] = True  # Set to True to enable info messages
DEBUG_JSON: Final[bool] = False  # Set to True to enable saving intermediate data as json files


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
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

    parser.add_argument(
        "--output-card-list", "-o", default="card_list.txt", help="Output file with card list for deck."
    )

    args = parser.parse_args(argv)

    # Convert lists to tuples for consistency
    args.commander_names = tuple(args.commander_names)
    args.themes = tuple(args.themes) if args.themes else (None,)

    if not (args.synergy_threshold >= 0 and args.synergy_threshold <= 1):
        msg = "Must be between 0 and 1."
        parser.error(msg)

    if not (args.inclusion_threshold >= 0 and args.inclusion_threshold <= 1):
        msg = "Must be between 0 and 1."
        parser.error(msg)

    if not (args.price_threshold >= 0):
        msg = "Must be >= 0."
        parser.error(msg)

    return args


def _run(args: argparse.Namespace) -> None:
    edhrec = edhrec_client.create_edhrec_client()
    card_groups: list[Iterable[str] | Mapping[str, object]] = []

    for commander_name in args.commander_names:
        if VERBOSE:
            print(f"Processing commander: {commander_name}")
        for theme in args.themes:
            if VERBOSE:
                print(f"Processing theme: {theme}")
            data = edhrec.get_commander_data(commander_name, None, theme)
            cards = deck_builder.collect_eligible_cards(
                data["container"]["json_dict"]["cardlists"],
                synergy_threshold=args.synergy_threshold,
                inclusion_threshold=args.inclusion_threshold,
            )

            data = edhrec.get_commander_data(commander_name, "budget", theme)
            cards_budget = deck_builder.collect_eligible_cards(
                data["container"]["json_dict"]["cardlists"],
                synergy_threshold=args.synergy_threshold,
                inclusion_threshold=args.inclusion_threshold,
            )

            cards = deck_builder.filter_candidate_prices(
                cards,
                edhrec.get_card_list(list(cards)),
                vendor=args.vendor,
                price_threshold=args.price_threshold,
            )
            cards_budget = deck_builder.filter_candidate_prices(
                cards_budget,
                edhrec.get_card_list(list(cards_budget)),
                vendor=args.vendor,
                price_threshold=args.price_threshold,
            )

            if DEBUG_JSON:
                with Path(f"cards_{theme}.json").open("w") as fp:
                    json.dump(cards, fp, indent=2, sort_keys=True)

                with Path(f"cards_budget_{theme}.json").open("w") as fp:
                    json.dump(cards_budget, fp, indent=2, sort_keys=True)

            average_deck = edhrec.get_commanders_average_deck(commander_name, None, theme)
            avg_deck = deck_builder.average_deck_names(average_deck["decklist"])
            avg_deck = deck_builder.filter_average_deck_prices(
                avg_deck,
                edhrec.get_card_list(avg_deck),
                vendor=args.vendor,
                price_threshold=args.price_threshold,
            )

            average_deck_budget = edhrec.get_commanders_average_deck(commander_name, "budget", theme)
            avg_deck_budget = deck_builder.average_deck_names(average_deck_budget["decklist"])
            avg_deck_budget = deck_builder.filter_average_deck_prices(
                avg_deck_budget,
                edhrec.get_card_list(avg_deck_budget),
                vendor=args.vendor,
                price_threshold=args.price_threshold,
            )

            if DEBUG_JSON:
                with Path(f"avg_deck_{theme}.json").open("w") as fp:
                    json.dump(avg_deck, fp, indent=2, sort_keys=True)

                with Path(f"avg_deck_budget_{theme}.json").open("w") as fp:
                    json.dump(avg_deck_budget, fp, indent=2, sort_keys=True)

            card_groups.extend((cards, cards_budget, avg_deck, avg_deck_budget))

    occurrences = deck_builder.count_card_occurrences(*card_groups)
    cards_main_deck, cards_considering = deck_builder.classify_cards(
        occurrences, theme_count=len(args.themes), commander_count=len(args.commander_names)
    )
    deck_builder.write_card_list(Path(args.output_card_list), cards_main_deck, cards_considering)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _run(args)
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
