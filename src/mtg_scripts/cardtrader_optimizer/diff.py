from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def compare_prices(cards_en: Mapping[str, int], cards_any: Mapping[str, int], minimum: int, maximum: int) -> None:
    total_diff = 0
    for card in sorted(cards_en.keys() & cards_any.keys()):
        diff = cards_en[card] - cards_any[card]
        if minimum <= diff <= maximum:
            total_diff += diff
            diff_dollars = round(diff / 100, 2)
            print(f"{card=} {diff_dollars=}")
    total_diff_dollars = round(total_diff / 100, 2)
    print(f"Total diff: {total_diff_dollars=}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare card prices in cents.")
    parser.add_argument("--english", type=Path, default=Path("en.json"))
    parser.add_argument("--any-language", type=Path, default=Path("any.json"))
    parser.add_argument("--min-diff", type=int, default=50)
    parser.add_argument("--max-diff", type=int, default=1000)
    args = parser.parse_args(argv)
    try:
        with args.english.open(encoding="utf-8") as source:
            cards_en = json.load(source)
        with args.any_language.open(encoding="utf-8") as source:
            cards_any = json.load(source)
        compare_prices(cards_en, cards_any, args.min_diff, args.max_diff)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
