from __future__ import annotations

import re

import pytest

from mtg_scripts.common.card_lists import normalize_card_name, parse_card_line, parse_card_list


def _legacy_counts(lines: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw_line in lines:
        line = re.sub(r"\s+", " ", raw_line).strip()
        name = line
        quantity = 1
        parts = line.split(" ", maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            name = parts[1]
            quantity = int(parts[0])
        if name:
            key = re.sub(r"(.*?[^/]) *//? *([^/].*)", r"\1 // \2", name).lower()
            counts[key] = counts.get(key, 0) + quantity
    return counts


@pytest.mark.parametrize(
    "line",
    [
        "",
        " \t ",
        "Sol Ring",
        "2 Sol Ring",
        "  2\tSol   Ring  ",
        "0 Forest",
        "2",
        "-2 Forest",
        "1.5 Forest",
        "2x Forest",
        "Fire/Ice",
        "Fire // Ice",
        "2 Fire/ Ice",
        "Who/What/When/Where/Why",
        "Avacyn's Pilgrim",
        "Gruul D\u00fchr",
        "Stra\u00dfe",
        "STRASSE",
        "1 Sol Ring (cmm) 123 *F*",
        "# section",
    ],
)
def test_plain_list_matches_existing_parser(line: str) -> None:
    assert parse_card_list([line]) == _legacy_counts([line])


def test_duplicates_and_split_separators_aggregate_without_folding_new_collisions() -> None:
    lines = ["2 Fire/Ice", "3 FIRE // ICE", "Sol Ring", "2 sol ring", "Stra\u00dfe", "STRASSE"]
    assert parse_card_list(lines) == {"fire // ice": 5, "sol ring": 3, "stra\u00dfe": 1, "strasse": 1}


def test_display_name_is_separate_from_matching_key() -> None:
    assert parse_card_line(" 2 Avacyn's   Pilgrim ") == (2, "Avacyn's Pilgrim")
    assert normalize_card_name("Avacyn's Pilgrim") == "avacyn's pilgrim"


def test_parser_accepts_a_single_pass_iterable() -> None:
    assert parse_card_list(iter(["1 Forest", "2 Forest"])) == {"forest": 3}
