from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Count identical lines across text files.")
    parser.add_argument("files", nargs="+", type=Path, help="Text files to count.")
    args = parser.parse_args(argv)
    counter: Counter[str] = Counter()

    try:
        for file_path in args.files:
            with file_path.open("r", encoding="utf-8") as f:
                for line in f:
                    counter[line.rstrip("\n")] += 1
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 1

    # Sort by count (descending), then alphabetically
    sorted_lines: list[tuple[str, int]] = sorted(counter.items(), key=lambda x: (-x[1], x[0]))

    for line, count in sorted_lines:
        print(f"{count}\t{line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
