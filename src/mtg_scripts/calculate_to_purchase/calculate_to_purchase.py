from __future__ import annotations

import argparse
import sys
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Final

import requests

from mtg_scripts.common.json_io import write_json
from mtg_scripts.services.moxfield import fetch_deck, normalize_moxfield_deck_id

from . import parsing, purchase_calculator
from .purchase_calculator import PurchaseInputs

if TYPE_CHECKING:
    from collections.abc import Sequence

DEBUG_JSON: Final[bool] = False  # Set to True to enable saving intermediate data as json files


def parse_deck_id_arg(deck_id_list: list[str]) -> tuple[str | tuple[str, ...], ...]:
    """Parse a list of strings into a tuple of deck IDs.

    Supports nested tuples using parentheses, e.g. "(id1,id2)".
    """
    result: list[str | tuple[str, ...]] = []
    for raw_item in deck_id_list:
        item = raw_item.strip()
        # Allow both (id1,id2) and simple id forms
        if item.startswith("(") and item.endswith(")"):
            # Safely parse content inside parentheses as a tuple of strings
            inner = item[1:-1].strip()
            ids: tuple[str, ...] = tuple(normalize_moxfield_deck_id(i.strip()) for i in inner.split(",") if i.strip())
            result.append(ids)
        else:
            result.append(normalize_moxfield_deck_id(item))
    return tuple(result)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--collection-file",
        "-c",
        default="collection.csv",
        help=(
            "Path to the owned cards file (required). "
            "Export it from https://moxfield.com/collection (More -> Export CSV)."
        ),
    )

    parser.add_argument(
        "--purchased-file",
        "-p",
        help=(
            "Path to the purchased cards file (default: purchased.txt). "
            "Populate by copy-pasting the list of cards from https://www.cardtrader.com/orders/buyer_future_order."
        ),
    )

    parser.add_argument(
        "--filter-out-file",
        "-f",
        help=("Path to file listing cards to filter out (default: filter_out.txt)."),
    )

    parser.add_argument(
        "--want-deck-ids",
        "-w",
        nargs="+",
        required=True,
        help="Moxfield deck IDs you want cards for. Group variants using parentheses, e.g. '(id1,id2)'.",
    )

    parser.add_argument(
        "--have-deck-ids",
        "-v",
        nargs="*",
        default=[],
        help="Moxfield deck IDs you already have. Group variants using parentheses, e.g. '(id3,id4)'.",
    )

    parser.add_argument(
        "--buy-considering",
        "-b",
        action="store_true",
        help="Whether to buy cards in the considering pile.",
    )

    parser.add_argument(
        "--to-purchase-file",
        default="to_purchase.txt",
        help="Path to output file listing all cards to purchase (default: to_purchase.txt).",
    )

    parser.add_argument(
        "--to-purchase-decks-file",
        default="to_purchase_decks.txt",
        help="Path to output file listing cards to purchase for decks (default: to_purchase_decks.txt).",
    )

    parser.add_argument(
        "--to-purchase-considering-file",
        default="to_purchase_considering.txt",
        help="Path to output file listing considering cards (default: to_purchase_considering.txt).",
    )

    args = parser.parse_args(argv)

    args.want_deck_ids = parse_deck_id_arg(args.want_deck_ids)
    args.have_deck_ids = parse_deck_id_arg(args.have_deck_ids)

    return args


def download_deck(deck_id: str) -> tuple[dict[str, int], dict[str, int]]:
    deck_id = normalize_moxfield_deck_id(deck_id)
    headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"}
    data = fetch_deck(
        deck_id,
        get=partial(requests.get, headers=headers, timeout=30),
        transport_errors=(requests.RequestException,),
    )
    if DEBUG_JSON:
        write_json(Path(deck_id + ".json"), data)
    deck: dict[str, int] = {
        card_name.lower(): card_data["quantity"] for card_name, card_data in data["commanders"].items()
    }
    for card_name, card_data in data["sideboard"].items():
        deck[card_name.lower()] = deck.get(card_name.lower(), 0) + card_data["quantity"]
    for card_name, card_data in data["companions"].items():
        deck[card_name.lower()] = deck.get(card_name.lower(), 0) + card_data["quantity"]
    for card_name, card_data in data["mainboard"].items():
        deck[card_name.lower()] = deck.get(card_name.lower(), 0) + card_data["quantity"]
    maybeboard: dict[str, int] = {
        card_name.lower(): card_data["quantity"] for card_name, card_data in data["maybeboard"].items()
    }
    return deck, maybeboard


def _run(args: argparse.Namespace) -> None:
    purchased_cards: dict[str, int] = {}
    if args.purchased_file is not None:
        purchased_cards = parsing.parse_purchased_file(args.purchased_file)

    filter_out_list: set[str] = set()
    if args.filter_out_file is not None:
        filter_out_list = parsing.parse_filter_out_file(args.filter_out_file)

    if DEBUG_JSON:
        write_json(Path("purchased.json"), purchased_cards)

    owned_cards = parsing.parse_owned_file(args.collection_file)

    if DEBUG_JSON:
        write_json(Path("owned.json"), owned_cards)

    have = purchase_calculator.combine_inventory(owned_cards, purchased_cards)

    if DEBUG_JSON:
        write_json(Path("have.json"), have)

    cards_in_decks: dict[str, int] = {}
    considering_cards: dict[str, int] = {}
    for deck_id in args.want_deck_ids + args.have_deck_ids:
        if isinstance(deck_id, tuple):
            main_decks: list[dict[str, int]] = []
            maybeboards: list[dict[str, int]] = []
            for dck_id in deck_id:
                mdck, mbbd = download_deck(dck_id)
                main_decks.append(mdck)
                maybeboards.append(mbbd)
            main_deck = purchase_calculator.merge_deck_variants(main_decks)
            maybeboard = purchase_calculator.merge_deck_variants(maybeboards)
        else:
            main_deck, maybeboard = download_deck(deck_id)

        if deck_id in args.want_deck_ids:
            cards_in_decks, considering_cards = purchase_calculator.add_wanted_deck(
                cards_in_decks, considering_cards, main_deck, maybeboard, filter_out_list
            )
        if deck_id in args.have_deck_ids:
            have = purchase_calculator.allocate_have_deck(have, main_deck)

    if DEBUG_JSON:
        write_json(Path("in_decks.json"), cards_in_decks)
        write_json(Path("considering.json"), considering_cards)

    calculation = purchase_calculator.calculate_purchase(
        PurchaseInputs(
            cards_in_decks=cards_in_decks,
            considering_cards=considering_cards,
            available=have,
            purchased=purchased_cards,
            owned=owned_cards,
            buy_considering=args.buy_considering,
        )
    )

    if DEBUG_JSON:
        write_json(Path("need.json"), calculation.need)
        write_json(Path("need_decks.json"), calculation.need_decks)
        write_json(Path("need_considering.json"), calculation.need_considering)

    if DEBUG_JSON:
        write_json(Path("avoided.json"), calculation.avoided)
        write_json(Path("avoided_owned.json"), calculation.avoided_owned)
        write_json(Path("avoided_purchased.json"), calculation.avoided_purchased)

    _write_count_file(args.to_purchase_file, calculation.to_purchase)
    _write_count_file(args.to_purchase_decks_file, calculation.to_purchase_decks)

    if args.buy_considering:
        _write_count_file(args.to_purchase_considering_file, calculation.to_purchase_considering)


def _write_count_file(path: str | Path, counts: dict[str, int]) -> None:
    with Path(path).open("w") as output:
        output.writelines(f"{amount} {card_name}\n" for card_name, amount in sorted(counts.items()))


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
