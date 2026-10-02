from mtg_scripts.print_picker.models import DeckEntry  # type: ignore[import-untyped]
from mtg_scripts.print_picker.view_model import CardSlot, sort_slots  # type: ignore[import-untyped]


def test_card_slot_reports_loading_phases_and_errors() -> None:
    slot = CardSlot(entry=DeckEntry(quantity=1, name="Test Card"))

    assert slot.status_text == ""
    slot.info_loading = True
    assert slot.status_text == "Loading info..."

    slot.info_loading = False
    slot.image_loading = True
    assert slot.status_text == "Loading image..."

    slot.error = "Card not found"
    assert slot.status_text == "Card not found"


def test_import_slots_sort_alphabetically_before_resolution() -> None:
    slots = [
        CardSlot(entry=DeckEntry(quantity=1, name="zebra")),
        CardSlot(entry=DeckEntry(quantity=1, name="Alpha")),
        CardSlot(entry=DeckEntry(quantity=1, name="bravo")),
    ]

    ordered = sort_slots(slots, include_name=True)

    assert [slot.name for slot in ordered] == ["Alpha", "bravo", "zebra"]
