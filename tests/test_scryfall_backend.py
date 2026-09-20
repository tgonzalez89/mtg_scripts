from typing import Any

from mtg_scripts.print_picker.scryfall_backend import ScryfallBackend


def _backend_with_cards(cards: list[dict[str, Any]]) -> ScryfallBackend:
    backend = ScryfallBackend.__new__(ScryfallBackend)
    index = {
        "by_name": {"llanowar elves": cards},
        "by_front_face_name": {},
        "by_flavor_name": {},
        "by_oracle_id": {},
    }
    backend._default_index = lambda _progress_callback=None: index
    backend._oracle_index = lambda _progress_callback=None: index
    return backend


def test_parse_all_printing_hint_combinations() -> None:
    cases = {
        "1 Llanowar Elves": {},
        "1 Llanowar Elves 3": {"collector_number": "3"},
        "1 Llanowar Elves *F*": {"is_foil": True},
        "1 Llanowar Elves 3 *F*": {"collector_number": "3", "is_foil": True},
        "1 Llanowar Elves (m12)": {"set": "m12"},
        "1 Llanowar Elves (m12) *F*": {"set": "m12", "is_foil": True},
        "1 Llanowar Elves (m12) 182": {"set": "m12", "collector_number": "182"},
        "1 Llanowar Elves (m12) 182 *F*": {
            "set": "m12",
            "collector_number": "182",
            "is_foil": True,
        },
    }

    for line, expected_hint in cases.items():
        item = ScryfallBackend.parse_card_line(line)
        assert item.get("printing_hint", {}) == expected_hint


def test_printing_hints_filter_set_number_and_finish() -> None:
    cards = [
        {
            "id": "m12",
            "name": "Llanowar Elves",
            "set": "m12",
            "collector_number": "182",
            "finishes": ["nonfoil", "foil"],
        },
        {
            "id": "set",
            "name": "Llanowar Elves",
            "set": "abc",
            "collector_number": "3",
            "finishes": ["nonfoil"],
        },
        {"id": "foil", "name": "Llanowar Elves", "set": "abc", "collector_number": "3★", "finishes": ["foil"]},
    ]
    backend = _backend_with_cards(cards)

    cases = {
        "1 Llanowar Elves": "m12",
        "1 Llanowar Elves 3": "set",
        "1 Llanowar Elves *F*": "m12",
        "1 Llanowar Elves 3 *F*": "foil",
        "1 Llanowar Elves (m12)": "m12",
        "1 Llanowar Elves (m12) *F*": "m12",
        "1 Llanowar Elves (m12) 182": "m12",
        "1 Llanowar Elves (m12) 182 *F*": "m12",
    }

    for line, expected_id in cases.items():
        item = ScryfallBackend.parse_card_line(line)
        card = backend.search_card(item["name"], item.get("printing_hint"))
        assert card is not None, line
        assert card["id"] == expected_id, line


def test_collector_numbers_are_exact_without_foil_hint() -> None:
    cards = [
        {
            "id": "m12-182",
            "name": "Llanowar Elves",
            "set": "m12",
            "collector_number": "182",
            "finishes": ["nonfoil", "foil"],
        },
        {
            "id": "pdmu-1-foil",
            "name": "Llanowar Elves",
            "set": "pdmu",
            "collector_number": "1★",
            "finishes": ["foil"],
        },
        {
            "id": "7ed-231",
            "name": "Llanowar Elves",
            "set": "7ed",
            "collector_number": "231",
            "finishes": ["nonfoil"],
        },
        {
            "id": "7ed-231-foil",
            "name": "Llanowar Elves",
            "set": "7ed",
            "collector_number": "231★",
            "finishes": ["foil"],
        },
    ]
    backend = _backend_with_cards(cards)

    exact_nonfoil_record = backend.search_card("Llanowar Elves", {"collector_number": "1"})
    assert exact_nonfoil_record is not None
    assert exact_nonfoil_record["id"] == "pdmu-1-foil"

    exact_foil_record = backend.search_card("Llanowar Elves", {"collector_number": "1", "is_foil": True})
    assert exact_foil_record is not None
    assert exact_foil_record["id"] == "pdmu-1-foil"

    no_fuzzy_match = backend.search_card("Llanowar Elves", {"collector_number": "18"})
    assert no_fuzzy_match is None

    no_broad_foil_match = backend.search_card("Llanowar Elves", {"collector_number": "23", "is_foil": True})
    assert no_broad_foil_match is None

    nonfoil_match = backend.search_card("Llanowar Elves", {"collector_number": "231"})
    assert nonfoil_match is not None
    assert nonfoil_match["id"] == "7ed-231"

    explicit_nonfoil_match = backend.search_card(
        "Llanowar Elves", {"collector_number": "231", "is_foil": False}
    )
    assert explicit_nonfoil_match is not None
    assert explicit_nonfoil_match["id"] == "7ed-231"


def test_set_only_foil_hint_uses_shared_finish_record() -> None:
    cards = [
        {
            "id": "fdc-213",
            "name": "Llanowar Elves",
            "set": "fdc",
            "collector_number": "213",
            "finishes": ["nonfoil", "foil"],
        }
    ]
    backend = _backend_with_cards(cards)

    for line in ("1 Llanowar Elves (FDC)", "1 Llanowar Elves (FDC) *F*"):
        item = ScryfallBackend.parse_card_line(line)
        card = backend.search_card(item["name"], item.get("printing_hint"))
        assert card is not None
        assert card["id"] == "fdc-213"
