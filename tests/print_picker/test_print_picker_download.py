from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from PIL import Image

from mtg_scripts.print_picker.models import CardPrint, DeckEntry  # type: ignore[import-untyped]
from mtg_scripts.print_picker.print_picker import App  # type: ignore[import-untyped]
from mtg_scripts.print_picker.view_model import CardSlot  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


class _ImageBackend:
    def __init__(self, images: Sequence[Image.Image]) -> None:
        self.images = images

    def load_images(self, _card: object, *, high_quality: bool) -> tuple[Image.Image, ...]:
        assert high_quality
        return tuple(self.images)


def _save_slot_images(
    tmp_path: Path,
    images: Sequence[Image.Image],
    *,
    slot_index: int = 1,
    quantity: int = 1,
    make_copies_unique: bool = False,
) -> list[Path]:
    card = CardPrint(backend="test", print_id="test-print", set_code="set", collector_number="1")
    slot = CardSlot(entry=DeckEntry(quantity=quantity, name="Test Card"), resolved=card)
    app = cast(
        "App",
        SimpleNamespace(
            backend=_ImageBackend(images),
            _safe_filename=App._safe_filename,
            _make_copy_unique=App._make_copy_unique,
        ),
    )
    App._save_slot_images(
        app,
        str(tmp_path),
        slot_index,
        slot,
        card,
        make_copies_unique=make_copies_unique,
    )
    return sorted(tmp_path.glob(f"{slot_index:03d}_*.png"))


def test_download_images_are_unchanged_by_default(tmp_path: Path) -> None:
    source = Image.new("RGBA", (32, 32), (80, 120, 160, 255))
    original_pixels = source.tobytes()

    paths = _save_slot_images(tmp_path, [source], quantity=3)

    assert len(paths) == 3
    assert len({hashlib.sha256(path.read_bytes()).digest() for path in paths}) == 1
    assert all(Image.open(path).tobytes() == original_pixels for path in paths)
    assert source.tobytes() == original_pixels


def test_unique_downloads_distinguish_slots_copies_and_faces(tmp_path: Path) -> None:
    source = Image.new("RGBA", (32, 32), (80, 120, 160, 255))
    original_pixels = source.tobytes()

    first_slot_paths = _save_slot_images(
        tmp_path,
        [source, source.copy()],
        slot_index=1,
        quantity=2,
        make_copies_unique=True,
    )
    second_slot_paths = _save_slot_images(
        tmp_path,
        [source],
        slot_index=2,
        make_copies_unique=True,
    )
    paths = [*first_slot_paths, *second_slot_paths]

    assert len(paths) == 5
    assert len({hashlib.sha256(path.read_bytes()).digest() for path in paths}) == len(paths)
    for path in paths:
        with Image.open(path) as saved_image:
            assert saved_image.tobytes() != original_pixels
            for y in range(source.height):
                for x in range(source.width):
                    source_pixel = cast("tuple[int, int, int, int]", source.getpixel((x, y)))
                    saved_pixel = cast("tuple[int, int, int, int]", saved_image.getpixel((x, y)))
                    assert all(
                        abs(original - changed) <= 1
                        for original, changed in zip(source_pixel, saved_pixel, strict=True)
                    )
    assert source.tobytes() == original_pixels
