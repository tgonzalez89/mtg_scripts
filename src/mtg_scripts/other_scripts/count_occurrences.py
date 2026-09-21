import argparse
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Count identical lines across text files.")
    parser.add_argument("files", nargs="+", type=Path, help="Text files to count.")
    args = parser.parse_args()
    counter: Counter[str] = Counter()

    for file_path in args.files:
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                counter[line.rstrip("\n")] += 1

    # Sort by count (descending), then alphabetically
    sorted_lines: list[tuple[str, int]] = sorted(counter.items(), key=lambda x: (-x[1], x[0]))

    for line, count in sorted_lines:
        print(f"{count}\t{line}")


if __name__ == "__main__":
    main()
