"""Read-only SQLite store for the Scryfall bulk card data.

The store replaces an in-memory index of the full bulk payload. Building streams
the compressed JSONL line by line, so no more than one card is resident at a
time, and reading opens the database as `mode=ro&immutable=1` so the rows for
the handful of cards on screen are the only ones ever materialized.
"""

import gzip
import json
import re
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from .models import CardFace, CardPrint

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
    from pathlib import Path

BACKEND_NAME: Final[str] = "scryfall"
STORE_SCHEMA_VERSION: Final[int] = 5
_BATCH_SIZE: Final[int] = 5_000

NAME_KIND_PRIMARY: Final[int] = 0
NAME_KIND_FRONT_FACE: Final[int] = 1
NAME_KIND_FLAVOR: Final[int] = 2

_SCHEMA: Final[str] = """
CREATE TABLE prints(
  print_id TEXT PRIMARY KEY,
  oracle_key TEXT NOT NULL,
  name TEXT NOT NULL,
  set_code TEXT NOT NULL,
  set_name TEXT NOT NULL,
  set_type TEXT NOT NULL,
  games TEXT NOT NULL,
  collector_number TEXT NOT NULL,
  released_on TEXT NOT NULL,
  finishes TEXT NOT NULL,
  is_default INTEGER NOT NULL,
  is_token INTEGER NOT NULL,
  faces_json TEXT NOT NULL
);
CREATE TABLE names(
  norm_name TEXT NOT NULL,
  print_id TEXT NOT NULL,
  kind INTEGER NOT NULL
);
"""

_INDEXES: Final[str] = """
CREATE INDEX idx_names_norm ON names(norm_name);
CREATE INDEX idx_prints_oracle ON prints(oracle_key);
"""

_PRINT_COLUMNS: Final[str] = (
    "print_id, oracle_key, name, set_code, set_name, set_type, games, "
    "collector_number, released_on, finishes, is_default, is_token, faces_json"
)
_PRINT_PLACEHOLDERS: Final[str] = ",".join("?" * len(_PRINT_COLUMNS.split(",")))

type _Row = tuple[str, str, str, str, str, str, str, str, str, str, int, int, str]

_TOKEN_LAYOUTS: Final[frozenset[str]] = frozenset({"token", "double_faced_token"})


@dataclass(frozen=True, slots=True)
class ScryfallPrint(CardPrint):
    """A printing plus the extras Scryfall needs to choose between printings.

    These live here rather than on `CardPrint` because they are Scryfall's own
    vocabulary: its finish names, its notion of a "default" printing, and its
    token layouts. Nothing outside this backend reads them.
    """

    set_type: str = ""
    # Which platforms this printing exists on, e.g. {"paper", "mtgo"}.
    games: frozenset[str] = frozenset()
    finishes: frozenset[str] = frozenset()
    is_default_print: bool = False
    is_token: bool = False


@dataclass(frozen=True, slots=True)
class NameMatch:
    """A printing, and how directly the searched name matched it.

    `kind` is one of the `NAME_KIND_*` values; lower means a more direct match.
    Callers use it to prefer, say, a card actually named "Shock" over one whose
    flavor name happens to be "Shock".
    """

    kind: int
    card: ScryfallPrint


def store_path(directory: Path, version: str) -> Path:
    """Return the on-disk path for a store built from the given bulk version."""
    return directory / f"cards-{version}-v{STORE_SCHEMA_VERSION}.db"


def discard_superseded(directory: Path, keep: Path) -> None:
    """Delete everything the store at `keep` makes redundant.

    That is every older store (and any index pickle from before this module
    existed), plus the compressed bulk sources: they are build inputs only, and
    a later rebuild is triggered by Scryfall publishing new download URIs, which
    means fetching new files regardless.
    """
    for stale in (*directory.glob("cards-*.db"), *directory.glob("cards-*.pickle")):
        if stale != keep:
            stale.unlink(missing_ok=True)
    if keep.exists():
        for source in directory.glob("*.jsonl.gz"):
            source.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def build(destination: Path, oracle_path: Path, default_path: Path) -> None:
    """Build the store from the oracle and default bulk files, atomically."""
    default_ids = _read_oracle_ids(oracle_path)
    temporary_path = destination.with_suffix(destination.suffix + ".tmp")
    temporary_path.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary_path)
    try:
        connection.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
        connection.executescript(_SCHEMA)
        _insert_cards(connection, _iter_cards(default_path), default_ids)
        connection.executescript(_INDEXES)
        connection.commit()
    finally:
        connection.close()
    temporary_path.replace(destination)


def build_from_cards(destination: Path, cards: Iterable[dict[str, Any]]) -> None:
    """Build a store directly from card payloads. Used by tests and fixtures."""
    materialized = list(cards)
    default_ids = {str(card["id"]) for card in materialized if card.get("id")}
    destination.unlink(missing_ok=True)
    connection = sqlite3.connect(destination)
    try:
        connection.executescript(_SCHEMA)
        _insert_cards(connection, iter(materialized), default_ids)
        connection.executescript(_INDEXES)
        connection.commit()
    finally:
        connection.close()


def _read_oracle_ids(oracle_path: Path) -> set[str]:
    """Collect the printing ids that Scryfall considers the default for a card."""
    identifiers: set[str] = set()
    for card in _iter_cards(oracle_path):
        card_id = card.get("id")
        if card_id:
            identifiers.add(str(card_id))
    return identifiers


def _iter_cards(path: Path) -> Iterator[dict[str, Any]]:
    """Yield one parsed card per line, never holding the whole file in memory."""
    with gzip.open(path, "rt", encoding="utf-8") as bulk_file:
        for line in bulk_file:
            if line.strip():
                yield json.loads(line)


def _insert_cards(connection: sqlite3.Connection, cards: Iterator[dict[str, Any]], default_ids: set[str]) -> None:
    print_rows: list[_Row] = []
    name_rows: list[tuple[str, str, int]] = []
    for card in cards:
        card_id = card.get("id")
        if not card_id:
            continue
        print_id = str(card_id)
        print_rows.append(_print_row(card, print_id, is_default=print_id in default_ids))
        name_rows.extend(_name_rows(card, print_id))
        if len(print_rows) >= _BATCH_SIZE:
            _flush(connection, print_rows, name_rows)
    _flush(connection, print_rows, name_rows)


def _flush(connection: sqlite3.Connection, print_rows: list[_Row], name_rows: list[tuple[str, str, int]]) -> None:
    if print_rows:
        connection.executemany(
            f"INSERT OR REPLACE INTO prints({_PRINT_COLUMNS}) VALUES({_PRINT_PLACEHOLDERS})",
            print_rows,
        )
        print_rows.clear()
    if name_rows:
        connection.executemany("INSERT INTO names(norm_name, print_id, kind) VALUES(?,?,?)", name_rows)
        name_rows.clear()
    connection.commit()


def _print_row(card: dict[str, Any], print_id: str, *, is_default: bool) -> _Row:
    faces = _faces(card)
    return (
        print_id,
        _oracle_key(card),
        str(card.get("name", "")),
        str(card.get("set", "")),
        str(card.get("set_name", "")),
        str(card.get("set_type", "")),
        json.dumps(sorted(str(game) for game in card.get("games") or [])),
        str(card.get("collector_number", "")),
        str(card.get("released_at", "")),
        json.dumps(list(card.get("finishes") or [])),
        int(is_default),
        int(_is_token(card)),
        json.dumps([[face.name, face.image_url, face.image_url_hq] for face in faces]),
    )


def _is_token(card: dict[str, Any]) -> bool:
    return card.get("layout") in _TOKEN_LAYOUTS or str(card.get("type_line", "")).startswith("Token")


def _oracle_key(card: dict[str, Any]) -> str:
    oracle_id = card.get("oracle_id")
    if oracle_id:
        return str(oracle_id)
    for face in card.get("card_faces") or []:
        face_oracle_id = face.get("oracle_id")
        if face_oracle_id:
            return str(face_oracle_id)
    # Fall back to the printing itself so the card still groups with something
    # stable rather than colliding with every other key-less card.
    return f"print:{card.get('id', '')}"


def _faces(card: dict[str, Any]) -> tuple[CardFace, ...]:
    """Return the renderable faces, collapsing single-image cards to one face."""
    image_uris = card.get("image_uris") or {}
    if image_uris:
        return (
            CardFace(
                name=str(card.get("name", "")),
                image_url=image_uris.get("normal"),
                image_url_hq=image_uris.get("png") or image_uris.get("large"),
            ),
        )
    faces: list[CardFace] = []
    for face in (card.get("card_faces") or [])[:2]:
        face_uris = face.get("image_uris") or {}
        faces.append(
            CardFace(
                name=str(face.get("name", "")),
                image_url=face_uris.get("normal"),
                image_url_hq=face_uris.get("png") or face_uris.get("large"),
            )
        )
    if faces:
        return tuple(faces)
    return (CardFace(name=str(card.get("name", ""))),)


def _name_rows(card: dict[str, Any], print_id: str) -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int]] = []
    seen: set[tuple[str, int]] = set()

    def add(raw_name: object, kind: int) -> None:
        if not raw_name:
            return
        normalized = normalize_name(str(raw_name))
        if normalized and (normalized, kind) not in seen:
            seen.add((normalized, kind))
            rows.append((normalized, print_id, kind))

    add(card.get("name"), NAME_KIND_PRIMARY)
    card_faces = card.get("card_faces") or []
    if card_faces:
        add(card_faces[0].get("name"), NAME_KIND_FRONT_FACE)
    add(card.get("flavor_name"), NAME_KIND_FLAVOR)
    for face in card_faces:
        add(face.get("flavor_name"), NAME_KIND_FLAVOR)
    return rows


def normalize_name(name: str) -> str:
    """Normalize a card name for lookup: canonical `//` separator, casefolded."""
    return re.sub(r"(?<=\S)\s*/+\s*(?=\S)", " // ", name).strip().casefold()


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


class CardStore:
    """Read-only handle onto a built card store."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro&immutable=1",
            uri=True,
            check_same_thread=False,
        )

    def close(self) -> None:
        self._connection.close()

    @property
    def path(self) -> Path:
        return self._path

    def by_name(self, names: Sequence[str], *, include_flavor: bool = True) -> dict[str, list[NameMatch]]:
        """Return matches grouped by the normalized name that found them.

        Each group is ordered by how directly it matched — full card name first,
        then front-face name, then flavor name — and newest printing first
        within a kind, so callers can simply take the first acceptable entry.
        A printing that matches more than one way is reported once, under its
        most direct kind.
        """
        if not names:
            return {}
        normalized = list(dict.fromkeys(normalize_name(name) for name in names if name.strip()))
        if not normalized:
            return {}
        kinds = (
            (NAME_KIND_PRIMARY, NAME_KIND_FRONT_FACE, NAME_KIND_FLAVOR)
            if include_flavor
            else (NAME_KIND_PRIMARY, NAME_KIND_FRONT_FACE)
        )
        name_slots = ",".join("?" * len(normalized))
        kind_slots = ",".join("?" * len(kinds))
        query = (
            f"SELECT n.norm_name, n.kind, {_qualified(_PRINT_COLUMNS, 'p')} "  # noqa: S608
            "FROM names n JOIN prints p ON p.print_id = n.print_id "
            f"WHERE n.norm_name IN ({name_slots}) AND n.kind IN ({kind_slots}) "
            "ORDER BY n.kind, p.released_on DESC, p.print_id"
        )
        grouped: dict[str, dict[str, NameMatch]] = {name: {} for name in normalized}
        for row in self._connection.execute(query, (*normalized, *kinds)):
            card = _row_to_print(row[2:])
            grouped[row[0]].setdefault(card.print_id, NameMatch(kind=int(row[1]), card=card))
        return {name: list(matches.values()) for name, matches in grouped.items()}

    def printings_of(self, card_key: str) -> list[ScryfallPrint]:
        """Return every printing sharing a card key."""
        if not card_key:
            return []
        query = f"SELECT {_PRINT_COLUMNS} FROM prints WHERE oracle_key = ?"  # noqa: S608
        return [_row_to_print(row) for row in self._connection.execute(query, (card_key,))]


def _qualified(columns: str, alias: str) -> str:
    return ", ".join(f"{alias}.{column.strip()}" for column in columns.split(","))


def _row_to_print(row: Sequence[object]) -> ScryfallPrint:
    faces = tuple(
        CardFace(name=name, image_url=url, image_url_hq=url_hq) for name, url, url_hq in json.loads(str(row[12]))
    )
    return ScryfallPrint(
        backend=BACKEND_NAME,
        print_id=str(row[0]),
        card_key=str(row[1]),
        name=str(row[2]),
        set_code=str(row[3]),
        set_name=str(row[4]),
        set_type=str(row[5]),
        games=frozenset(json.loads(str(row[6]))),
        collector_number=str(row[7]),
        released_on=str(row[8]),
        finishes=frozenset(json.loads(str(row[9]))),
        faces=faces,
        is_default_print=bool(row[10]),
        is_token=bool(row[11]),
    )
