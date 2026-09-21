import json
import re
import threading
import time
from typing import TYPE_CHECKING, Final, TypedDict, cast

from . import scryfall_store
from .card_backend import CardBackend, ProgressCallback
from .models import CardPrint, DeckEntry, PrintQuery, Resolution, matches_set_code
from .scryfall_store import CardStore, NameMatch, ScryfallPrint

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    import requests

SCRYFALL_BULK_DATA_URL: Final[str] = "https://api.scryfall.com/bulk-data"
SCRYFALL_BULK_TYPES: Final[tuple[str, str]] = ("oracle_cards", "default_cards")
SCRYFALL_BULK_METADATA_MAX_AGE: Final[int] = 24 * 60 * 60
USER_AGENT: Final[str] = "mtg-print-picker/1.0 (contact: local)"

# Scryfall's own vocabulary, deliberately kept out of the shared model.
FOIL: Final[str] = "foil"
NONFOIL: Final[str] = "nonfoil"
FOIL_STAR: Final[str] = "★"
FOIL_SUFFIX: Final[str] = "*F*"

# Sets whose contents are not cards you put in a deck: Art Series and other
# memorabilia, token sheets, Unglued-style minigame cards, and oversized
# Vanguard avatars.
NONPLAYABLE_SET_TYPES: Final[frozenset[str]] = frozenset({"memorabilia", "token", "minigame", "vanguard"})

# A printing's `games` lists the platforms it exists on. Physical printings are
# what this tool is for, so they win over digital-only ones.
PAPER: Final[str] = "paper"


class _ScryfallBulkDataEntry(TypedDict, total=False):
    """Fields used from a Scryfall `/bulk-data` entry."""

    type: str
    jsonl_download_uri: str
    updated_at: str


class _ScryfallBulkDataResponse(TypedDict, total=False):
    """Shape of the Scryfall `/bulk-data` list response."""

    data: list[_ScryfallBulkDataEntry]


class ScryfallBackend(CardBackend):
    supports_progress = True

    def __init__(self, cache_dir: str | Path | None = None, session: requests.Session | None = None) -> None:
        super().__init__(cache_dir, session)
        self.bulk_dir = self.json_cache_dir.parent / "bulk"
        self.bulk_dir.mkdir(parents=True, exist_ok=True)
        self._store_lock = threading.Lock()
        self._store: CardStore | None = None

    @property
    def user_agent(self) -> str:
        return USER_AGENT

    # -- import parsing -----------------------------------------------------

    @staticmethod
    def parse_line(line: str) -> DeckEntry:
        quantity_match = re.match(r"^(\d+)\s+(.+)$", line.strip())
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        card_text = quantity_match.group(2).strip() if quantity_match else line.strip()

        foil_match = re.search(r"\s+(\*F\*|\*|★)$", card_text)
        is_foil = True if foil_match else None
        if foil_match:
            card_text = card_text[: foil_match.start()].rstrip()

        set_and_collector_match = re.match(r"^(.+?)\s+\(([A-Za-z0-9]+)\)\s+([A-Za-z0-9][A-Za-z0-9-]*)$", card_text)
        set_match = re.match(r"^(.+?)\s+\(([A-Za-z0-9]+)\)$", card_text)
        collector_match = re.match(r"^(.+?)\s+([0-9][A-Za-z0-9-]*)$", card_text)
        if set_and_collector_match:
            name, set_code, collector_number = set_and_collector_match.groups()
        elif set_match:
            name, set_code = set_match.groups()
            collector_number = None
        elif collector_match:
            name, collector_number = collector_match.groups()
            set_code = None
        else:
            name, set_code, collector_number = card_text, None, None

        return DeckEntry(
            quantity=quantity,
            name=name.strip(),
            query=PrintQuery(set_code=set_code, collector_number=collector_number, foil=is_foil),
        )

    @staticmethod
    def export_card_text(card: CardPrint, entry: DeckEntry) -> str:
        """Format as `Name (set) 123`, with a trailing `*F*` for foils."""
        raw_number = card.collector_number
        collector_number = raw_number.removesuffix(FOIL_STAR).removesuffix("*").rstrip()
        is_foil = entry.query.foil is True or raw_number != collector_number

        parts = [card.name or entry.name]
        if card.set_code:
            parts.append(f"({card.set_code})")
        if collector_number:
            parts.append(collector_number)
        if is_foil:
            parts.append(FOIL_SUFFIX)
        return " ".join(parts)

    # -- resolution ---------------------------------------------------------

    def resolve(self, entries: Sequence[DeckEntry], progress: ProgressCallback | None = None) -> list[Resolution]:
        if not entries:
            return []
        store = self._card_store(progress)
        # One query for the whole deck, rather than one per line.
        candidates = store.by_name([entry.name for entry in entries])
        resolutions = [Resolution(entry=entry, card=self._select(candidates, entry)) for entry in entries]
        self._retry_as_whole_name(store, resolutions)
        return resolutions

    def _retry_as_whole_name(self, store: CardStore, resolutions: list[Resolution]) -> None:
        """Re-read lines whose trailing number turned out not to be one.

        `Specimen 73` parses as the card "Specimen", printing 73 — but it is
        also a card name in its own right. The reading is genuinely ambiguous,
        and only a failed lookup tells us which was meant.
        """
        pending: dict[int, DeckEntry] = {}
        for index, resolution in enumerate(resolutions):
            query = resolution.entry.query
            if resolution.card is None and query.collector_number and not query.set_code:
                pending[index] = DeckEntry(
                    quantity=resolution.entry.quantity,
                    name=f"{resolution.entry.name} {query.collector_number}",
                    query=PrintQuery(foil=query.foil),
                )
        if not pending:
            return
        candidates = store.by_name([entry.name for entry in pending.values()])
        for index, entry in pending.items():
            card = self._select(candidates, entry)
            if card is not None:
                resolutions[index] = Resolution(entry=entry, card=card)

    def _select(self, candidates: dict[str, list[NameMatch]], entry: DeckEntry) -> ScryfallPrint | None:
        matches = candidates.get(scryfall_store.normalize_name(entry.name), [])
        if not entry.query:
            return _select_by_name_only(matches)
        # An explicit set or number already pins the printing, so every match
        # competes regardless of how its name matched.
        cards = [match.card for match in matches]
        identity_matches = [card for card in cards if _matches_identity(card, entry.query)]
        if not identity_matches:
            return None
        if entry.query.foil is True:
            foil_matches = [card for card in identity_matches if FOIL in card.finishes]
            return _best(foil_matches or identity_matches)
        if entry.query.foil is False:
            return _best([card for card in identity_matches if NONFOIL in card.finishes])
        nonfoil_matches = [card for card in identity_matches if NONFOIL in card.finishes]
        return _best(nonfoil_matches or identity_matches)

    def printings_of(self, card: CardPrint, progress: ProgressCallback | None = None) -> Sequence[CardPrint]:
        return self._card_store(progress).printings_of(card.card_key)

    # -- store lifecycle ----------------------------------------------------

    def _card_store(self, progress: ProgressCallback | None = None) -> CardStore:
        with self._store_lock:
            if self._store is not None:
                return self._store

            metadata = self._load_bulk_metadata()
            download_uris = [str(metadata[bulk_type]["jsonl_download_uri"]) for bulk_type in SCRYFALL_BULK_TYPES]
            version = self._cache_name("\n".join(download_uris))[:16]
            path = scryfall_store.store_path(self.bulk_dir, version)
            if not path.exists():
                self._build_store(path, download_uris, progress)
            scryfall_store.discard_superseded(self.bulk_dir, keep=path)
            self._store = CardStore(path)
            return self._store

    def _build_store(self, path: Path, download_uris: list[str], progress: ProgressCallback | None) -> None:
        bulk_paths: list[Path] = []
        for bulk_type, download_uri in zip(SCRYFALL_BULK_TYPES, download_uris, strict=True):
            bulk_version = self._cache_name(download_uri)[:16]
            bulk_path = self.bulk_dir / f"{bulk_type}-{bulk_version}.jsonl.gz"
            if not bulk_path.exists():
                self._download_bulk_file(download_uri, bulk_path, progress)
            bulk_paths.append(bulk_path)
        _report_progress(progress, "Building card database...", 0, 0)
        scryfall_store.build(path, bulk_paths[0], bulk_paths[1])

    def close(self) -> None:
        with self._store_lock:
            if self._store is not None:
                self._store.close()
                self._store = None
        super().close()

    def clear_json_cache(self) -> None:
        super().clear_json_cache()
        with self._store_lock:
            if self._store is not None:
                self._store.close()
                self._store = None
            for bulk_file in self.bulk_dir.iterdir():
                if bulk_file.is_file():
                    bulk_file.unlink()

    # -- bulk data ----------------------------------------------------------

    def _load_bulk_metadata(self) -> dict[str, _ScryfallBulkDataEntry]:
        metadata_path = self.bulk_dir / "metadata.json"
        metadata_is_current = metadata_path.exists() and (
            time.time() - metadata_path.stat().st_mtime < SCRYFALL_BULK_METADATA_MAX_AGE
        )
        if metadata_is_current:
            with metadata_path.open("r", encoding="utf-8") as metadata_file:
                metadata: dict[str, _ScryfallBulkDataEntry] = json.load(metadata_file)
            if all(bulk_type in metadata for bulk_type in SCRYFALL_BULK_TYPES):
                return metadata

        response = self.session.get(SCRYFALL_BULK_DATA_URL, timeout=20)
        response.raise_for_status()
        bulk_data_response = cast("_ScryfallBulkDataResponse", response.json())
        metadata = {entry["type"]: entry for entry in bulk_data_response.get("data", [])}
        missing_types = [bulk_type for bulk_type in SCRYFALL_BULK_TYPES if bulk_type not in metadata]
        if missing_types:
            msg = f"Scryfall bulk data is missing: {', '.join(missing_types)}"
            raise ValueError(msg)
        with metadata_path.open("w", encoding="utf-8") as metadata_file:
            json.dump(metadata, metadata_file)
        return metadata

    def _download_bulk_file(self, url: str, destination: Path, progress: ProgressCallback | None = None) -> None:
        temporary_path = destination.with_suffix(destination.suffix + ".tmp")
        response = self.session.get(url, timeout=120, stream=True)
        response.raise_for_status()
        label = f"Downloading {destination.stem}..."
        try:
            total = int(response.headers.get("content-length", 0)) if hasattr(response, "headers") else 0
            downloaded = 0
            _report_progress(progress, label, downloaded, total)
            with temporary_path.open("wb") as output_file:
                if hasattr(response, "iter_content"):
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output_file.write(chunk)
                            downloaded += len(chunk)
                            _report_progress(progress, label, downloaded, total)
                else:
                    output_file.write(response.content)
                    _report_progress(progress, label, len(response.content), total)
            temporary_path.replace(destination)
        finally:
            close = getattr(response, "close", None)
            if close:
                close()
            if temporary_path.exists():
                temporary_path.unlink()


def _select_by_name_only(matches: list[NameMatch]) -> ScryfallPrint | None:
    """Choose a printing for a bare card name.

    The most direct kind of name match wins outright: if the line names a
    printing's flavor name, that printing *is* what was asked for, and must not
    be traded for the plain card's default printing.
    """
    for kind in sorted({match.kind for match in matches}):
        chosen = _preferred_printing([match.card for match in matches if match.kind == kind])
        if chosen is not None:
            return chosen
    return None


def _preferred_printing(group: list[ScryfallPrint]) -> ScryfallPrint | None:
    """Pick within one match kind: Scryfall's default printing, nonfoil first."""
    # A flavor-named printing is a specific alternate-art card and so is almost
    # never the default printing, hence the fallback to the whole group.
    pool = [card for card in group if card.is_default_print] or group
    # A line with no finish requested means the ordinary version, so skip
    # foil-only printings when a nonfoil one exists.
    nonfoil = [card for card in pool if NONFOIL in card.finishes]
    return _best(nonfoil or pool)


def _matches_identity(card: ScryfallPrint, query: PrintQuery) -> bool:
    """Return whether a printing matches the set and number the line asked for."""
    if not matches_set_code(card, query):
        return False
    if not query.collector_number:
        return True
    actual = card.collector_number.casefold()
    requested = query.collector_number.casefold()
    # Scryfall suffixes a foil-only printing's number with a star.
    return actual in (requested, f"{requested}{FOIL_STAR}")


def _best(candidates: list[ScryfallPrint]) -> ScryfallPrint | None:
    """Pick the most likely intended printing."""
    return min(candidates, key=_preference) if candidates else None


def _preference(card: ScryfallPrint) -> tuple[bool, bool]:
    """Rank printings: real deck cards first, then physical ones. Lower is better.

    This only breaks ties. Equally-ranked printings keep the store's ordering —
    most direct name match first, then newest — and a demoted printing still
    wins when it is the only one available.
    """
    return _is_nonplayable(card), PAPER not in card.games


def _is_nonplayable(card: ScryfallPrint) -> bool:
    """Return whether a printing is a collectible rather than a deck card.

    Art Series cards (`Forest // Forest` and friends) live in `memorabilia`
    sets and match by front-face name, so without this they can win a plain
    name lookup over the real card.
    """
    return card.is_token or card.set_type in NONPLAYABLE_SET_TYPES


def _report_progress(progress: ProgressCallback | None, message: str, current: int, total: int) -> None:
    if progress:
        progress(message, current, total)
