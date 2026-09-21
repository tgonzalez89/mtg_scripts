"""Backend-agnostic domain model for the print picker.

Every type here is immutable and describes only what any card game has: a card,
the editions it was printed in, and what an import line asked for. Anything a
particular game invents — Scryfall's oracle ids, foil-star collector numbers and
finish lists, RiftCodex's printing codes — stays inside that game's backend,
which extends `CardPrint` privately when it needs to carry more.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CardFace:
    """One printed face of a card."""

    name: str = ""
    image_url: str | None = None
    image_url_hq: str | None = None


@dataclass(frozen=True, slots=True)
class CardPrint:
    """One physical printing of a card.

    Immutable, so it is safe to share across threads and across views without
    defensive copying. Backends subclass this to attach their own selection
    data; nothing outside a backend should depend on those extras.
    """

    backend: str
    print_id: str
    # Identifies the card a printing is *of*, so a card's printings can be
    # grouped. Each backend decides what makes two printings the same card.
    card_key: str = ""
    name: str = ""
    set_code: str = ""
    set_name: str = ""
    collector_number: str = ""
    released_on: str = ""
    faces: tuple[CardFace, ...] = ()

    def image_urls(self, *, high_quality: bool = False) -> tuple[str, ...]:
        """Return the image URLs to load for this printing, front face first."""
        urls = ((face.image_url_hq if high_quality else face.image_url) for face in self.faces)
        return tuple(url for url in urls if url)


@dataclass(frozen=True, slots=True)
class PrintQuery:
    """The printing an import line asked for, if it asked for one at all.

    These are the constraints a user can express in any game's import syntax.
    Deciding whether a printing satisfies them is the backend's job, because
    what counts as a match differs per game.
    """

    set_code: str | None = None
    collector_number: str | None = None
    foil: bool | None = None

    def __bool__(self) -> bool:
        return not (self.set_code is None and self.collector_number is None and self.foil is None)


@dataclass(frozen=True, slots=True)
class DeckEntry:
    """One parsed import line."""

    quantity: int
    name: str
    query: PrintQuery = field(default_factory=PrintQuery)


@dataclass(frozen=True, slots=True)
class Resolution:
    """The outcome of resolving one `DeckEntry` against a backend."""

    entry: DeckEntry
    card: CardPrint | None = None
    error: str | None = None


def display_label(card: CardPrint) -> str:
    """Return a readable set and collector-number label for a printing."""
    return f"{card.set_name} ({card.set_code.upper()}) #{card.collector_number}"


type SortKey = tuple[str, float, str, tuple[tuple[int, int | str], ...]]


def sort_key(card: CardPrint | None, *, include_name: bool = False) -> SortKey:
    """Return the ordering key for a printing: newest release first."""
    if card is None:
        return "", float("inf"), "", ()
    name_key = card.name.casefold() if include_name else ""
    return (
        name_key,
        _release_sort_key(card.released_on),
        card.set_code.casefold(),
        _collector_sort_key(card.collector_number),
    )


def _release_sort_key(released_on: str) -> float:
    if not released_on:
        return float("inf")
    try:
        timestamp = datetime.fromisoformat(released_on).timestamp()
    except ValueError:
        return float("inf")
    return -timestamp


def _collector_sort_key(collector_number: str) -> tuple[tuple[int, int | str], ...]:
    parts = re.findall(r"\d+|\D+", collector_number)
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in parts)


def matches_set_code(card: CardPrint, query: PrintQuery) -> bool:
    """Return whether a printing is from the set `query` asked for, if any."""
    return not query.set_code or card.set_code.casefold() == query.set_code.casefold()
