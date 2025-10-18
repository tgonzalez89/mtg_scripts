import sys
from collections import Counter
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: python count_occurrences.py file1.txt file2.txt ...")
        sys.exit(1)

    file_paths = sys.argv[1:]
    counter = Counter()

    for file_path in file_paths:
        with Path(file_path).open() as f:
            for line in f:
                counter[line.rstrip("\n")] += 1

    # Sort by count (descending), then alphabetically
    sorted_lines = sorted(counter.items(), key=lambda x: (-x[1], x[0]))

    for line, count in sorted_lines:
        print(f"{count}\t{line}")


if __name__ == "__main__":
    main()
