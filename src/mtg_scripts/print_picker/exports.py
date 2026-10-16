"""Pure Print Picker export formatting and image-download planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from PIL import Image

    from .models import CardPrint, DeckEntry
    from .view_model import CardSlot

UNIQUE_IMAGE_TOO_SMALL = "Image is too small to encode a unique copy identity."
IMAGE_PIXEL_ACCESS_UNAVAILABLE = "Unable to access image pixels."


@dataclass(frozen=True, slots=True)
class ImageDownloadTarget:
    copy_number: int
    face_index: int
    path: Path


@dataclass(frozen=True, slots=True)
class ImageDownloadRequest:
    folder: Path
    slot_index: int
    slot_name: str
    quantity: int
    set_code: str
    collector_number: str
    face_count: int


def safe_filename(name: str) -> str:
    return "".join(character for character in name if character.isalnum() or character in " ._-").rstrip()


def plan_image_downloads(request: ImageDownloadRequest) -> tuple[ImageDownloadTarget, ...]:
    safe_name = safe_filename(request.slot_name)
    safe_set = safe_filename(request.set_code)
    safe_number = safe_filename(request.collector_number)
    return tuple(
        ImageDownloadTarget(
            copy_number,
            face_index,
            request.folder
            / f"{request.slot_index:03d}_{copy_number:02d}_{safe_name}_{safe_set}_{safe_number}_face{face_index}.png",
        )
        for copy_number in range(1, request.quantity + 1)
        for face_index in range(1, request.face_count + 1)
    )


def make_copy_unique(image: Image.Image, slot_index: int, copy_number: int, face_index: int) -> Image.Image:
    image_copy = image.convert("RGBA")
    identity = b"".join(value.to_bytes(8, byteorder="big") for value in (slot_index, copy_number, face_index))
    required_bits = len(identity) * 8
    if image_copy.width * image_copy.height * 3 < required_bits:
        raise ValueError(UNIQUE_IMAGE_TOO_SMALL)

    pixels = image_copy.load()
    if pixels is None:
        raise RuntimeError(IMAGE_PIXEL_ACCESS_UNAVAILABLE)
    for bit_index in range(required_bits):
        bit = (identity[bit_index // 8] >> (7 - bit_index % 8)) & 1
        pixel_index, channel = divmod(bit_index, 3)
        x = pixel_index % image_copy.width
        y = pixel_index // image_copy.width
        red, green, blue, alpha = cast("tuple[int, int, int, int]", pixels[x, y])
        if channel == 0:
            red = (red & 0xFE) | bit
        elif channel == 1:
            green = (green & 0xFE) | bit
        else:
            blue = (blue & 0xFE) | bit
        pixels[x, y] = (red, green, blue, alpha)
    return image_copy


def build_export_text(slots: Iterable[CardSlot], export_card_text: Callable[[CardPrint, DeckEntry], str]) -> str | None:
    combined: dict[str, int] = {}
    for slot in slots:
        card = slot.display_print
        if card is None:
            continue
        card_text = export_card_text(card, slot.entry)
        combined[card_text] = combined.get(card_text, 0) + slot.quantity
    if not combined:
        return None
    return "\n".join(f"{quantity} {card_text}" for card_text, quantity in combined.items()) + "\n"
