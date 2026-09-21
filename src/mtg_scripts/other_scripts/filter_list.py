import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove lines using a deny-list text file.")
    parser.add_argument("input_file", type=Path, help="Text file to filter.")
    parser.add_argument("remove_file", type=Path, help="Text file containing lines to remove.")
    args = parser.parse_args()

    with args.input_file.open("r", encoding="utf-8") as f1:
        lines1: set[str] = {line.rstrip("\n") for line in f1}
    with args.remove_file.open("r", encoding="utf-8") as f2:
        lines2: set[str] = {line.rstrip("\n") for line in f2}

    filtered: list[str] = [line for line in lines1 if line not in lines2]

    for line in filtered:
        print(line)


if __name__ == "__main__":
    main()
