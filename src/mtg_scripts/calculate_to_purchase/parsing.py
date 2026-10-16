"""Input parsing adapters for the purchase calculator."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from mtg_scripts.common.card_lists import normalize_card_name, parse_card_list


def parse_owned_file(path: str) -> dict[str, int]:
    """Parse and consolidate a Moxfield collection CSV by normalized card name."""
    owned_counts: dict[str, int] = {}

    with Path(path).open("r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        if reader.fieldnames is None:
            message = "Collection CSV is missing a header row."
            raise ValueError(message)
        name_field = next((field for field in reader.fieldnames if field.lower() == "name"), None)
        count_field = next((field for field in reader.fieldnames if field.lower() == "count"), None)
        if name_field is None or name_field == "" or count_field is None or count_field == "":
            message = f"Expected columns 'Name' and 'Count' not found in {path}"
            raise ValueError(message)

        for row in reader:
            name = row[name_field].strip().lower()
            try:
                count = int(row[count_field])
            except ValueError:
                count = 0
            owned_counts[name] = owned_counts.get(name, 0) + count
    return owned_counts


def parse_purchased_file(path: str | Path) -> dict[str, int]:
    with Path(path).open("r", encoding="utf-8") as purchased_file:
        text = purchased_file.read()
    pattern = re.compile(r"([^\n]+)\s+\w+ (\d+)\s+\1", re.DOTALL)
    matches = pattern.findall(text)
    if not matches:
        return parse_card_list(text.splitlines())

    purchased: dict[str, int] = {}
    for raw_name, raw_amount in matches:
        name = normalize_card_name(raw_name.strip())
        purchased[name] = purchased.get(name, 0) + int(raw_amount.strip())
    return purchased


def parse_filter_out_file(path: str | Path) -> set[str]:
    excluded: set[str] = set()
    with Path(path).open("r", encoding="utf-8") as filter_file:
        for line in filter_file:
            name = line.strip()
            if name:
                excluded.add(normalize_card_name(name))
    return excluded
