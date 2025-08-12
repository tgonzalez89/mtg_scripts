import sys
from pathlib import Path


def main():
    if len(sys.argv) < 4:
        print("Usage: python filter_list.py list.txt to_remove_from_list.txt")
        sys.exit(1)

    file1_path = sys.argv[1]
    file2_path = sys.argv[2]

    with Path(file1_path).open() as f1:
        lines1 = set(line.rstrip("\n") for line in f1)
    with Path(file2_path).open() as f2:
        lines2 = set(line.rstrip("\n") for line in f2)

    filtered = [line for line in lines1 if line not in lines2]

    for line in filtered:
        print(line)


if __name__ == "__main__":
    main()
