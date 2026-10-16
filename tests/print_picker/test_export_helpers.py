from __future__ import annotations

from typing import TYPE_CHECKING

from mtg_scripts.print_picker.exports import ImageDownloadRequest, build_export_text, plan_image_downloads
from mtg_scripts.print_picker.models import CardPrint, DeckEntry
from mtg_scripts.print_picker.view_model import CardSlot

if TYPE_CHECKING:
    from pathlib import Path


def test_download_planner_sanitizes_names_and_preserves_copy_face_order(tmp_path: Path) -> None:
    targets = plan_image_downloads(ImageDownloadRequest(tmp_path, 4, "Bad:/Name*", 2, "AB/C", "1/2", 2))

    assert [target.path.name for target in targets] == [
        "004_01_BadName_ABC_12_face1.png",
        "004_01_BadName_ABC_12_face2.png",
        "004_02_BadName_ABC_12_face1.png",
        "004_02_BadName_ABC_12_face2.png",
    ]


def test_export_aggregates_backend_text_and_omits_unresolved_slots() -> None:
    card = CardPrint(backend="test", print_id="print-1", name="Forest", set_code="tst")
    slots = [
        CardSlot(entry=DeckEntry(quantity=2, name="Forest"), resolved=card),
        CardSlot(entry=DeckEntry(quantity=3, name="Forest"), resolved=card),
        CardSlot(entry=DeckEntry(quantity=1, name="Missing")),
    ]

    assert build_export_text(slots, lambda printing, _entry: f"{printing.name} ({printing.set_code})") == (
        "5 Forest (tst)\n"
    )
    assert build_export_text([slots[-1]], lambda printing, _entry: printing.name) is None
