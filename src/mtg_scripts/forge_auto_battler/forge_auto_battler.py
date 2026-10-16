from __future__ import annotations

import argparse
import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

from .runtime_config import TESSDATA_ENV_VAR, ForgeRunOptions, default_tessdata_dir, validate_tessdata_dir

if TYPE_CHECKING:
    from collections.abc import Sequence

FOUR_PLAYERS = 4
DEBUG: bool = True


def parse_arguments(argv: Sequence[str] | None = None) -> ForgeRunOptions:
    parser = argparse.ArgumentParser(
        description="Simulate 4-player free-for-all games in Forge using a list of deck names."
    )
    parser.add_argument("decks", type=str, nargs="+", help="List of deck names (minimum 4).")
    parser.add_argument("--min-matches", type=int, required=False, help="Min number of matches that need to be run.")
    parser.add_argument(
        "--tessdata-dir",
        type=Path,
        default=default_tessdata_dir(),
        help=f"Tesseract data directory (or set {TESSDATA_ENV_VAR}).",
    )
    args = parser.parse_args(argv)

    if len(args.decks) < FOUR_PLAYERS:
        msg = f"You must provide at least 4 deck names. Provided: {args.decks}"
        parser.error(msg)

    if DEBUG:
        print(f"Using decks: {args.decks}.")
        print(f"Min matches: {args.min_matches}.")
    return ForgeRunOptions(args.decks, args.min_matches, args.tessdata_dir)


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_arguments(argv)
    if sys.platform != "win32":
        print("Forge automation requires Windows.", file=sys.stderr)
        return 1
    try:
        tessdata_dir = validate_tessdata_dir(options.tessdata_dir)
        import_module("pywinauto")
        import_module("tesserocr")
        from .runtime import run_matches

        run_matches(options.decks, options.min_matches, tessdata_dir=tessdata_dir)
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
