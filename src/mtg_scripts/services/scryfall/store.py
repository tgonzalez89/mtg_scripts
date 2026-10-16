"""Versioned read-only SQLite store built by streaming Scryfall bulk JSONL."""

from __future__ import annotations

import gzip
import json
import re
import sqlite3
from typing import TYPE_CHECKING, Any, Final

from .models import ScryfallCard, ScryfallCardFace, ScryfallNameMatch

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
    from pathlib import Path

STORE_SCHEMA_VERSION: Final = 8
_BATCH_SIZE: Final = 5_000
NAME_KIND_PRIMARY: Final = 0
NAME_KIND_FRONT_FACE: Final = 1
NAME_KIND_FLAVOR: Final = 2
_TOKEN_LAYOUTS: Final = frozenset({"token", "double_faced_token"})

_SCHEMA: Final = """
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
  faces_json TEXT NOT NULL,
    oracle_text TEXT NOT NULL,
    color_identity TEXT NOT NULL,
    commander_legal INTEGER NOT NULL,
    type_line TEXT NOT NULL,
    mana_cost TEXT NOT NULL,
    mana_value REAL,
    power TEXT,
    toughness TEXT,
    usd TEXT,
    usd_foil TEXT,
    usd_etched TEXT,
    eur TEXT,
    eur_foil TEXT,
    tix TEXT
);
CREATE TABLE names(norm_name TEXT NOT NULL, print_id TEXT NOT NULL, kind INTEGER NOT NULL);
CREATE TABLE oracle_tags(tag_slug TEXT NOT NULL, oracle_id TEXT NOT NULL,
                         PRIMARY KEY(tag_slug, oracle_id));
CREATE TABLE oracle_tag_nodes(tag_id TEXT PRIMARY KEY, tag_slug TEXT NOT NULL);
CREATE TABLE oracle_tag_children(parent_id TEXT NOT NULL, child_id TEXT NOT NULL,
                                 PRIMARY KEY(parent_id, child_id));
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
_INDEXES: Final = """
CREATE INDEX idx_names_norm ON names(norm_name);
CREATE INDEX idx_prints_oracle ON prints(oracle_key);
CREATE INDEX idx_prints_set_collector ON prints(set_code, collector_number);
CREATE INDEX idx_oracle_tags_slug ON oracle_tags(tag_slug);
CREATE INDEX idx_oracle_tags_oracle ON oracle_tags(oracle_id);
CREATE INDEX idx_oracle_tag_nodes_slug ON oracle_tag_nodes(tag_slug);
CREATE INDEX idx_oracle_tag_children_parent ON oracle_tag_children(parent_id);
"""
_PRINT_COLUMNS: Final = (
    "print_id, oracle_key, name, set_code, set_name, set_type, games, collector_number, "
    "released_on, finishes, is_default, is_token, faces_json, oracle_text, color_identity, "
    "commander_legal, type_line, mana_cost, mana_value, power, toughness, usd, usd_foil, usd_etched, eur, eur_foil, tix"
)
_PRICE_FIELDS: Final = ("usd", "usd_foil", "usd_etched", "eur", "eur_foil", "tix")
_PRINT_PLACEHOLDERS: Final = ",".join("?" * len(_PRINT_COLUMNS.split(",")))
type _PrintRow = tuple[str | int | float | None, ...]


def normalize_name(name: str) -> str:
    """Canonicalize split separators and case for Scryfall card names."""
    return re.sub(r"(?<=\S)\s*/+\s*(?=\S)", " // ", name).strip().casefold()


def store_path(directory: Path, version: str) -> Path:
    return directory / f"cards-{version}-v{STORE_SCHEMA_VERSION}.db"


def validate_store(path: Path) -> bool:
    """Validate integrity and the complete current schema using a read-only handle."""
    if not path.is_file() or not re.search(rf"-v{STORE_SCHEMA_VERSION}(?:-[A-Za-z0-9-]+)?\.db$", path.name):
        return False
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            if integrity is None or str(integrity[0]) != "ok":
                return False
            tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {
                "prints",
                "names",
                "oracle_tags",
                "oracle_tag_nodes",
                "oracle_tag_children",
                "metadata",
            }.issubset(tables):
                return False
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(prints)")}
            return {column.strip() for column in _PRINT_COLUMNS.split(",")}.issubset(columns)
        finally:
            connection.close()
    except sqlite3.Error:
        return False


def build(  # noqa: PLR0913
    destination: Path,
    oracle_path: Path,
    default_path: Path,
    *,
    tags_path: Path | None = None,
    bulk_version: str = "",
    built_at: str = "",
) -> None:
    """Build a complete v8 store atomically from local bulk inputs."""
    default_ids = _read_oracle_ids(oracle_path)
    temporary_path = destination.with_name(f".{destination.name}.{sqlite3.sqlite_version}.tmp")
    temporary_path.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary_path)
    try:
        connection.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
        connection.executescript(_SCHEMA)
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES(?,?)",
            (
                ("schema_version", str(STORE_SCHEMA_VERSION)),
                ("bulk_version", bulk_version),
                ("built_at", built_at),
                ("oracle_tags_available", str(tags_path is not None).lower()),
            ),
        )
        _insert_cards(connection, _iter_cards(default_path), default_ids)
        if tags_path is not None:
            _insert_tags_from_file(connection, tags_path)
        connection.executescript(_INDEXES)
        connection.commit()
    except BaseException:
        connection.close()
        temporary_path.unlink(missing_ok=True)
        raise
    else:
        connection.close()
    temporary_path.replace(destination)


def build_from_cards(
    destination: Path,
    cards: Iterable[dict[str, Any]],
    *,
    tags: Iterable[dict[str, Any]] | None = None,
) -> None:
    """Build a small local fixture store; no network or bulk download is used."""
    materialized = list(cards)
    default_ids = {str(card["id"]) for card in materialized if card.get("id")}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    connection = sqlite3.connect(destination)
    try:
        connection.executescript(_SCHEMA)
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES(?,?)",
            (
                ("schema_version", str(STORE_SCHEMA_VERSION)),
                ("bulk_version", "fixture"),
                ("built_at", ""),
                ("oracle_tags_available", str(tags is not None).lower()),
            ),
        )
        _insert_cards(connection, iter(materialized), default_ids)
        if tags is not None:
            _insert_tags(connection, list(tags))
        connection.executescript(_INDEXES)
        connection.commit()
    finally:
        connection.close()


def _read_oracle_ids(oracle_path: Path) -> set[str]:
    identifiers: set[str] = set()
    for card in _iter_cards(oracle_path):
        card_id = card.get("id")
        if card_id:
            identifiers.add(str(card_id))
        oracle_id = card.get("oracle_id")
        if oracle_id:
            identifiers.add(str(oracle_id))
        for face in card.get("card_faces") or []:
            if isinstance(face, dict) and face.get("oracle_id"):
                identifiers.add(str(face["oracle_id"]))
    return identifiers


def _iter_cards(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as bulk:
        for line in bulk:
            if line.strip():
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    message = "Scryfall bulk JSONL entries must be objects."
                    raise ValueError(message)
                yield payload


def _insert_cards(connection: sqlite3.Connection, cards: Iterator[dict[str, Any]], default_ids: set[str]) -> None:
    print_rows: list[_PrintRow] = []
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


def _flush(
    connection: sqlite3.Connection,
    print_rows: list[_PrintRow],
    name_rows: list[tuple[str, str, int]],
) -> None:
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


def _tag_node(tag: dict[str, Any]) -> tuple[str, str] | None:
    slug = tag.get("slug")
    if tag.get("object") != "tag" or tag.get("type") != "oracle" or not isinstance(slug, str):
        return None
    tag_id = tag.get("id")
    normalized_slug = str(slug).casefold()
    identifier = tag_id if isinstance(tag_id, str) and tag_id else f"slug:{normalized_slug}"
    return identifier, normalized_slug


def _insert_tag_nodes(connection: sqlite3.Connection, tags: Iterator[dict[str, Any]]) -> None:
    rows: list[tuple[str, str]] = []
    for tag in tags:
        node = _tag_node(tag)
        if node is None:
            continue
        rows.append(node)
        if len(rows) >= _BATCH_SIZE:
            connection.executemany("INSERT OR REPLACE INTO oracle_tag_nodes(tag_id, tag_slug) VALUES(?,?)", rows)
            rows.clear()
    if rows:
        connection.executemany("INSERT OR REPLACE INTO oracle_tag_nodes(tag_id, tag_slug) VALUES(?,?)", rows)


def _insert_tag_records(connection: sqlite3.Connection, tags: Iterator[dict[str, Any]]) -> None:
    tagging_rows: list[tuple[str, str]] = []
    edge_rows: list[tuple[str, str]] = []
    for tag in tags:
        node = _tag_node(tag)
        if node is None:
            continue
        tag_id, slug = node
        tagging_rows.extend(_taggings_for_node(tag, slug))
        edge_rows.extend(_edges_for_node(tag, tag_id))

        if len(tagging_rows) >= _BATCH_SIZE:
            connection.executemany("INSERT OR IGNORE INTO oracle_tags(tag_slug, oracle_id) VALUES(?,?)", tagging_rows)
            tagging_rows.clear()
        if len(edge_rows) >= _BATCH_SIZE:
            connection.executemany(
                "INSERT OR IGNORE INTO oracle_tag_children(parent_id, child_id) VALUES(?,?)", edge_rows
            )
            edge_rows.clear()
    if tagging_rows:
        connection.executemany("INSERT OR IGNORE INTO oracle_tags(tag_slug, oracle_id) VALUES(?,?)", tagging_rows)
    if edge_rows:
        connection.executemany("INSERT OR IGNORE INTO oracle_tag_children(parent_id, child_id) VALUES(?,?)", edge_rows)
    connection.commit()


def _taggings_for_node(tag: dict[str, Any], slug: str) -> list[tuple[str, str]]:
    taggings = tag.get("taggings")
    if not isinstance(taggings, list):
        return []
    return [
        (slug, tagging["oracle_id"])
        for tagging in taggings
        if isinstance(tagging, dict) and isinstance(tagging.get("oracle_id"), str)
    ]


def _edges_for_node(tag: dict[str, Any], tag_id: str) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    parents = tag.get("parent_ids")
    if isinstance(parents, list):
        edges.extend((parent, tag_id) for parent in parents if isinstance(parent, str))
    children = tag.get("child_ids")
    if isinstance(children, list):
        edges.extend((tag_id, child) for child in children if isinstance(child, str))
    return edges


def _insert_tags(connection: sqlite3.Connection, tags: Sequence[dict[str, Any]]) -> None:
    _insert_tag_nodes(connection, iter(tags))
    _insert_tag_records(connection, iter(tags))


def _insert_tags_from_file(connection: sqlite3.Connection, path: Path) -> None:
    _insert_tag_nodes(connection, _iter_cards(path))
    _insert_tag_records(connection, _iter_cards(path))


def _print_row(card: dict[str, Any], print_id: str, *, is_default: bool) -> _PrintRow:
    face_values = _faces(card)
    oracle_key = _oracle_key(card, print_id)
    prices = card.get("prices") or {}
    return (
        print_id,
        oracle_key,
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
        json.dumps([[face.name, face.image_url, face.image_url_hq] for face in face_values]),
        str(card.get("oracle_text", "")),
        "".join(sorted(str(color) for color in card.get("color_identity") or [])),
        int((card.get("legalities") or {}).get("commander") == "legal"),
        str(card.get("type_line", "")),
        str(card.get("mana_cost", "")),
        _mana_value(card),
        _optional_text(card.get("power")),
        _optional_text(card.get("toughness")),
        *(_optional_text(prices.get(field)) for field in _PRICE_FIELDS),
    )


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _mana_value(card: dict[str, Any]) -> float | None:
    value = card.get("mana_value")
    if value is None:
        value = card.get("cmc")
    if not isinstance(value, (str, int, float)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _is_token(card: dict[str, Any]) -> bool:
    return card.get("layout") in _TOKEN_LAYOUTS or str(card.get("type_line", "")).startswith("Token")


def _oracle_key(card: dict[str, Any], print_id: str) -> str:
    oracle_id = card.get("oracle_id")
    if oracle_id:
        return str(oracle_id)
    for face in card.get("card_faces") or []:
        if isinstance(face, dict) and face.get("oracle_id"):
            return str(face["oracle_id"])
    return f"print:{print_id}"


def _faces(card: dict[str, Any]) -> tuple[ScryfallCardFace, ...]:
    image_uris = card.get("image_uris") or {}
    if isinstance(image_uris, dict) and image_uris:
        return (
            ScryfallCardFace(
                name=str(card.get("name", "")),
                image_url=image_uris.get("normal"),
                image_url_hq=image_uris.get("png") or image_uris.get("large"),
            ),
        )
    faces: list[ScryfallCardFace] = []
    for face in (card.get("card_faces") or [])[:2]:
        if not isinstance(face, dict):
            continue
        face_uris = face.get("image_uris") or {}
        if not isinstance(face_uris, dict):
            face_uris = {}
        faces.append(
            ScryfallCardFace(
                name=str(face.get("name", "")),
                image_url=face_uris.get("normal"),
                image_url_hq=face_uris.get("png") or face_uris.get("large"),
            )
        )
    return tuple(faces) if faces else (ScryfallCardFace(name=str(card.get("name", ""))),)


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
    faces = card.get("card_faces") or []
    if faces and isinstance(faces[0], dict):
        add(faces[0].get("name"), NAME_KIND_FRONT_FACE)
    add(card.get("flavor_name"), NAME_KIND_FLAVOR)
    for face in faces:
        if isinstance(face, dict):
            add(face.get("flavor_name"), NAME_KIND_FLAVOR)
    return rows


class CardStore:
    """Read-only handle onto a v8 Scryfall database."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True, check_same_thread=False)
        metadata = dict(self._connection.execute("SELECT key, value FROM metadata"))
        self.bulk_version = str(metadata.get("bulk_version", ""))
        self.built_at = str(metadata.get("built_at", ""))
        self.has_oracle_tags = metadata.get("oracle_tags_available") == "true"

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        self._connection.close()

    def by_name(self, names: Sequence[str], *, include_flavor: bool = True) -> dict[str, list[ScryfallNameMatch]]:
        normalized = list(dict.fromkeys(normalize_name(name) for name in names if name.strip()))
        if not normalized:
            return {}
        kinds = (
            (NAME_KIND_PRIMARY, NAME_KIND_FRONT_FACE, NAME_KIND_FLAVOR)
            if include_flavor
            else (NAME_KIND_PRIMARY, NAME_KIND_FRONT_FACE)
        )
        query = (
            f"SELECT n.norm_name, n.kind, {_qualified(_PRINT_COLUMNS, 'p')} "  # noqa: S608
            "FROM names n JOIN prints p ON p.print_id=n.print_id "
            f"WHERE n.norm_name IN ({','.join('?' for _ in normalized)}) "
            f"AND n.kind IN ({','.join('?' for _ in kinds)}) "
            "ORDER BY n.kind, p.released_on DESC, p.print_id"
        )
        grouped: dict[str, dict[str, ScryfallNameMatch]] = {name: {} for name in normalized}
        for row in self._connection.execute(query, (*normalized, *kinds)):
            card = _row_to_card(row[2:])
            grouped[str(row[0])].setdefault(card.print_id, ScryfallNameMatch(kind=int(row[1]), card=card))
        return {name: list(matches.values()) for name, matches in grouped.items()}

    def by_print_id(self, print_id: str) -> ScryfallCard | None:
        row = self._connection.execute(
            f"SELECT {_PRINT_COLUMNS} FROM prints WHERE print_id=?",  # noqa: S608
            (print_id,),
        ).fetchone()
        return None if row is None else _row_to_card(row)

    def printings_of(self, oracle_id: str) -> list[ScryfallCard]:
        if oracle_id == "":
            return []
        rows = self._connection.execute(
            f"SELECT {_PRINT_COLUMNS} FROM prints WHERE oracle_key=? ORDER BY released_on DESC, print_id",  # noqa: S608
            (oracle_id,),
        )
        return [_row_to_card(row) for row in rows]

    def cards_for_tag(self, slug: str) -> list[ScryfallCard]:
        if not self.has_oracle_tags:
            message = "Oracle tag bulk data is not available in this database."
            raise LookupError(message)
        normalized_slug = slug.removeprefix("otag:").casefold()
        slugs = self._tag_subtree_slugs(normalized_slug)
        if not slugs:
            return []
        placeholders = ",".join("?" for _ in slugs)
        rows = self._connection.execute(
            f"SELECT DISTINCT {_qualified(_PRINT_COLUMNS, 'p')} "  # noqa: S608
            "FROM oracle_tags t JOIN prints p ON p.oracle_key=t.oracle_id "
            f"WHERE t.tag_slug IN ({placeholders}) ORDER BY p.oracle_key, p.released_on DESC, p.print_id",
            slugs,
        )
        return [_row_to_card(row) for row in rows]

    def has_complete_tag_printings(self, slug: str) -> bool:
        if not self.has_oracle_tags:
            return False
        normalized_slug = slug.removeprefix("otag:").casefold()
        slugs = self._tag_subtree_slugs(normalized_slug)
        if not slugs:
            return False
        placeholders = ",".join("?" for _ in slugs)
        tagged_count = self._connection.execute(
            f"SELECT COUNT(DISTINCT oracle_id) FROM oracle_tags WHERE tag_slug IN ({placeholders})",  # noqa: S608
            slugs,
        ).fetchone()
        matched_count = self._connection.execute(
            "SELECT COUNT(DISTINCT t.oracle_id) "  # noqa: S608
            "FROM oracle_tags t JOIN prints p ON p.oracle_key=t.oracle_id "
            f"WHERE t.tag_slug IN ({placeholders})",
            slugs,
        ).fetchone()
        if tagged_count is None or matched_count is None:
            return False
        return int(tagged_count[0]) == int(matched_count[0])

    def _tag_subtree_slugs(self, slug: str) -> tuple[str, ...]:
        rows = self._connection.execute(
            "WITH RECURSIVE descendants(tag_id) AS ("
            "  SELECT tag_id FROM oracle_tag_nodes WHERE tag_slug=? "
            "  UNION "
            "  SELECT edge.child_id FROM oracle_tag_children edge "
            "  JOIN descendants parent ON edge.parent_id=parent.tag_id"
            ") "
            "SELECT DISTINCT node.tag_slug FROM oracle_tag_nodes node "
            "JOIN descendants ON descendants.tag_id=node.tag_id ORDER BY node.tag_slug",
            (slug,),
        )
        return tuple(str(row[0]) for row in rows)

    def metadata_value(self, key: str) -> str | None:
        row = self._connection.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row[0])


def card_from_payload(payload: dict[str, Any]) -> ScryfallCard:
    print_id = str(payload.get("id", ""))
    if not print_id:
        message = "Scryfall card payload is missing its printing id."
        raise ValueError(message)
    return _row_to_card(_print_row(payload, print_id, is_default=False))


def _row_to_card(row: Sequence[object]) -> ScryfallCard:
    faces = tuple(
        ScryfallCardFace(name=str(name), image_url=url, image_url_hq=url_hq)
        for name, url, url_hq in json.loads(str(row[12]))
    )
    return ScryfallCard(
        print_id=str(row[0]),
        oracle_id=str(row[1]),
        name=str(row[2]),
        set_code=str(row[3]),
        set_name=str(row[4]),
        set_type=str(row[5]),
        games=frozenset(json.loads(str(row[6]))),
        collector_number=str(row[7]),
        released_on=str(row[8]),
        finishes=frozenset(json.loads(str(row[9]))),
        is_default_print=bool(row[10]),
        is_token=bool(row[11]),
        faces=faces,
        oracle_text=str(row[13]),
        color_identity=frozenset(str(row[14])),
        commander_legal=bool(row[15]),
        type_line=str(row[16]),
        mana_cost=str(row[17]),
        mana_value=None if row[18] is None else float(str(row[18])),
        power=_optional_text(row[19]),
        toughness=_optional_text(row[20]),
        prices={field: _optional_text(value) for field, value in zip(_PRICE_FIELDS, row[21:], strict=True)},
    )


def _qualified(columns: str, alias: str) -> str:
    return ", ".join(f"{alias}.{column.strip()}" for column in columns.split(","))
