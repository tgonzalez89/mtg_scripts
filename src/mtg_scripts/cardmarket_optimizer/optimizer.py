from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TypeIs

from mtg_scripts.common.card_lists import parse_card_list
from mtg_scripts.common.json_io import read_json, write_json

from . import optimization
from .models import to_selected_offer

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .models import OfferRecord, SelectedOfferRecord, SellerAvailability


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--card-list",
        "-c",
        default="card_list.txt",
        help="Path to input text file containing the card list (default card_list.txt).",
    )
    parser.add_argument(
        "--sellers-database",
        "-s",
        default="sellers_database.json",
        help="Path to input sellers database file (default sellers_database.json).",
    )
    parser.add_argument(
        "--offers-database",
        "-o",
        default="offers_database.json",
        help="Path to input offers database file (default offers_database.json).",
    )
    parser.add_argument(
        "--selected-offers",
        "-e",
        default="selected_offers.json",
        help="Path to output selected offers file (default selected_offers.json).",
    )

    return parser.parse_args(argv)


def _load_offers(path: Path) -> dict[str, list[SelectedOfferRecord]]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        message = f"Offers database must contain an object: {path}"
        raise TypeError(message)
    result: dict[str, list[SelectedOfferRecord]] = {}
    for name, offers in payload.items():
        if not isinstance(name, str) or not isinstance(offers, list):
            message = f"Offers database has an invalid entry for {name!r}"
            raise TypeError(message)
        records: list[SelectedOfferRecord] = []
        for offer in offers:
            if not _is_offer_record(offer):
                message = f"Offers database contains a malformed offer for {name!r}"
                raise ValueError(message)
            records.append(to_selected_offer(offer))
        result[name] = records
    return result


def _is_offer_record(value: object) -> TypeIs[OfferRecord]:
    return (
        isinstance(value, dict)
        and isinstance(value.get("total_price"), (int, float))
        and isinstance(value.get("price"), (int, float))
        and isinstance(value.get("shipping_price"), (int, float))
        and isinstance(value.get("amount"), int)
        and isinstance(value.get("seller"), str)
    )


def _load_sellers(path: Path) -> dict[str, float]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        message = f"Sellers database must contain an object: {path}"
        raise TypeError(message)
    sellers: dict[str, float] = {}
    for seller, shipping_price in payload.items():
        if not isinstance(seller, str) or not isinstance(shipping_price, (int, float)):
            message = f"Sellers database contains an invalid entry for {seller!r}"
            raise TypeError(message)
        sellers[seller] = float(shipping_price)
    return sellers


def _complete_single_card_pass(
    new_card_list: dict[str, int],
    offers_path: Path,
    seller_availability: dict[str, SellerAvailability],
    selected_offers: dict[str, list[SelectedOfferRecord]],
    selected_sellers: set[str],
) -> tuple[dict[str, list[SelectedOfferRecord]], set[str]]:
    return optimization.run_algo(
        new_card_list,
        _load_offers(offers_path),
        seller_availability,
        selected_offers,
        selected_sellers,
    )


def _write_selection_report(path: Path, selected_offers: dict[str, list[SelectedOfferRecord]]) -> None:
    write_json(path, selected_offers)
    total_price, items_price, shipping_price, sellers = optimization.calc_total_prices(selected_offers)
    print(f"{total_price=} {items_price=} {shipping_price=} {len(sellers)=}")


def _run(args: argparse.Namespace) -> None:
    with Path(args.card_list).open("r", encoding="utf-8") as fp:
        card_list = parse_card_list(fp)

    offers_database = _load_offers(Path(args.offers_database))
    sellers_database = _load_sellers(Path(args.sellers_database))

    sellers_db_cards_available = optimization.build_seller_availability(card_list, offers_database, sellers_database)

    selected_offers, selected_sellers = optimization.run_algo(card_list, offers_database, sellers_db_cards_available)

    new_card_list = optimization.extract_single_card_sellers(selected_offers, selected_sellers)

    selected_offers, selected_sellers = _complete_single_card_pass(
        new_card_list,
        Path(args.offers_database),
        sellers_db_cards_available,
        selected_offers,
        selected_sellers,
    )
    _write_selection_report(Path(args.selected_offers), selected_offers)


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
