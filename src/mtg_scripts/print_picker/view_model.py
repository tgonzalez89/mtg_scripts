"""Mutable view state for the print picker GUI.

`CardSlot` is the GUI's own state. Backends never see it, and it never leaks
into anything cached, so widgets can mutate it freely without the defensive
copying the old dict-based records required.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import CardPrint, DeckEntry, display_label, sort_key

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PIL import Image


@dataclass(slots=True)
class CardSlot:
    """One deck entry and everything the GUI knows about rendering it.

    A slot is shared by the N `Card` widgets that show its copies, so updating
    it once updates every copy with no back-references to re-sync.
    """

    entry: DeckEntry
    resolved: CardPrint | None = None
    chosen: CardPrint | None = None
    error: str | None = None
    images: tuple[Image.Image, ...] = ()
    # The box `images` were fitted to, so the grid knows when it needs to
    # reload sharper art or can shrink back down.
    image_size: tuple[int, int] = (0, 0)
    face_index: int = 0
    image_loading: bool = False
    # Set for slots that represent a printing in the chooser, where the label
    # is the set and collector number rather than the card name.
    label_override: str | None = None

    @property
    def display_print(self) -> CardPrint | None:
        """Return the printing to show: the user's choice, else the resolved one."""
        return self.chosen or self.resolved

    @property
    def quantity(self) -> int:
        return self.entry.quantity

    @property
    def name(self) -> str:
        card = self.display_print
        return card.name if card and card.name else self.entry.name

    @property
    def label(self) -> str:
        if self.label_override is not None:
            return self.label_override
        return self.name

    @property
    def current_image(self) -> Image.Image | None:
        if not self.images:
            return None
        return self.images[self.face_index % len(self.images)]

    def advance_face(self) -> None:
        if len(self.images) > 1:
            self.face_index = (self.face_index + 1) % len(self.images)

    def release_images(self) -> None:
        self.images = ()
        self.image_size = (0, 0)
        self.face_index = 0
        self.image_loading = False


def printing_slot(card: CardPrint, fallback_name: str) -> CardSlot:
    """Build a one-copy slot representing an alternative printing."""
    return CardSlot(
        entry=DeckEntry(quantity=1, name=card.name or fallback_name),
        resolved=card,
        label_override=display_label(card),
    )


def sort_slots(slots: Sequence[CardSlot], *, include_name: bool) -> list[CardSlot]:
    """Order slots newest-printing-first, optionally grouping by card name.

    The name key comes from the slot rather than the printing so that entries
    that failed to resolve still sort under the name the user typed.
    """

    def key(slot: CardSlot) -> tuple[str, *tuple[object, ...]]:
        _, *rest = sort_key(slot.display_print)
        name_key = slot.name.casefold() if include_name else ""
        return (name_key, *rest)

    return sorted(slots, key=key)
