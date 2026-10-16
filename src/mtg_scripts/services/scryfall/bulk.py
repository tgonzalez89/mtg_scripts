"""Scryfall bulk metadata/download/build lifecycle with cross-process safety."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import sqlite3
import threading
import uuid
import warnings
from contextlib import suppress
from typing import TYPE_CHECKING, TypedDict, cast

from filelock import FileLock

from mtg_scripts.common.cache import CacheError, CachePaths, JsonDiskCache, canonical_cache_key
from mtg_scripts.common.http import HttpRequestError, JsonHttpClient

from . import store
from .store import CardStore

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from .models import ProgressCallback

BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
REQUIRED_BULK_TYPES = ("oracle_cards", "default_cards")
ORACLE_TAGS_TYPE = "oracle_tags"
BULK_METADATA_MAX_AGE = 24 * 60 * 60


class BulkDataEntry(TypedDict, total=False):
    type: str
    jsonl_download_uri: str
    updated_at: str


class BulkDataResponse(TypedDict, total=False):
    data: list[BulkDataEntry]


class ScryfallBulkData:
    """Lazily publish a schema-compatible local database generation."""

    def __init__(
        self,
        paths: CachePaths,
        http: JsonHttpClient,
        *,
        legacy_cache_dir: Path | None = None,
        offline: bool = False,
        clock: Callable[[], float],
    ) -> None:
        self.bulk_dir = paths.namespace("scryfall", "bulk")
        self.metadata_cache_dir = paths.namespace("scryfall", "metadata")
        self.bulk_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_cache = JsonDiskCache(self.metadata_cache_dir, provider="scryfall", clock=clock)
        self.http = http
        self.legacy_cache_dir = legacy_cache_dir
        self.offline = offline
        self._clock = clock
        self._lock = threading.RLock()
        self._store: CardStore | None = None
        self._retired: list[CardStore] = []

    @property
    def store(self) -> CardStore | None:
        with self._lock:
            return self._store

    def get_store(
        self,
        progress: ProgressCallback | None = None,
        *,
        force_refresh: bool = False,
    ) -> CardStore:
        with self._lock:
            if self._store is not None and not force_refresh:
                return self._store
            with FileLock(str(self.bulk_dir / ".build.lock")):
                self._migrate_legacy_store()
                if self.offline:
                    fallback = self._latest_usable_generation()
                    if fallback is None:
                        message = "Offline Scryfall mode has no compatible local card database; run once online first."
                        raise CacheError(message)
                    warnings.warn(
                        f"Using cached Scryfall database {fallback.name} in offline mode.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    path = fallback
                else:
                    try:
                        metadata = self._load_metadata(force_refresh=force_refresh)
                        uris = [str(metadata[bulk_type]["jsonl_download_uri"]) for bulk_type in REQUIRED_BULK_TYPES]
                        tags_entry = metadata.get(ORACLE_TAGS_TYPE)
                        tags_uri = str(tags_entry["jsonl_download_uri"]) if tags_entry is not None else None
                        version_input = "\n".join([*uris, *([tags_uri] if tags_uri is not None else [])])
                        version = hashlib.sha256(version_input.encode("utf-8")).hexdigest()[:16]
                        path = self._usable_generation(version)
                        if path is None:
                            canonical = store.store_path(self.bulk_dir, version)
                            path = (
                                canonical
                                if not canonical.exists()
                                else self.bulk_dir
                                / (f"cards-{version}-v{store.STORE_SCHEMA_VERSION}-rebuild-{uuid.uuid4().hex}.db")
                            )
                            self._build_store(path, version, uris, tags_uri, metadata, progress)
                        _require_valid_store(path)
                    except (
                        CacheError,
                        HttpRequestError,
                        OSError,
                        ValueError,
                        KeyError,
                        TypeError,
                        sqlite3.Error,
                    ) as error:
                        fallback = self._latest_usable_generation()
                        if fallback is None:
                            raise
                        warnings.warn(
                            f"Using cached Scryfall database {fallback.name} after refresh failed: {error}",
                            RuntimeWarning,
                            stacklevel=2,
                        )
                        path = fallback
                replacement = CardStore(path)
                if self._store is not None:
                    self._retired.append(self._store)
                self._store = replacement
                return replacement

    def refresh(self, progress: ProgressCallback | None = None) -> CardStore:
        self.metadata_cache.discard(canonical_cache_key("GET", BULK_DATA_URL))
        return self.get_store(progress, force_refresh=True)

    def close(self) -> None:
        with self._lock:
            if self._store is not None:
                self._store.close()
                self._store = None
            for retired in self._retired:
                retired.close()
            self._retired.clear()

    def _load_metadata(self, *, force_refresh: bool) -> dict[str, BulkDataEntry]:  # noqa: C901
        key = canonical_cache_key("GET", BULK_DATA_URL)
        if not force_refresh:
            legacy_paths = [self.bulk_dir / "metadata.json"]
            if self.legacy_cache_dir is not None:
                legacy_paths.append(self.legacy_cache_dir / "bulk" / "metadata.json")
            for legacy_path in legacy_paths:
                with suppress(OSError):
                    self.metadata_cache.import_legacy(
                        key,
                        legacy_path,
                        fetched_at=legacy_path.stat().st_mtime,
                        fresh_for_seconds=BULK_METADATA_MAX_AGE,
                    )
            cached = self.metadata_cache.get(key, max_age=BULK_METADATA_MAX_AGE)
            if cached is not None:
                parsed = _validate_bulk_metadata(cached.value)
                if parsed is not None:
                    return parsed
        response = cast("BulkDataResponse", self.http.get_json(BULK_DATA_URL, use_cache=False))
        entries = response.get("data")
        if not isinstance(entries, list):
            message = "Scryfall bulk metadata response is missing its data list."
            raise TypeError(message)
        metadata: dict[str, BulkDataEntry] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
                continue
            bulk_type = entry["type"]
            if bulk_type not in (*REQUIRED_BULK_TYPES, ORACLE_TAGS_TYPE):
                continue
            uri = entry.get("jsonl_download_uri")
            if not isinstance(uri, str) or not uri:
                if bulk_type in REQUIRED_BULK_TYPES:
                    message = f"Scryfall bulk metadata has an invalid URI for {bulk_type}."
                    raise ValueError(message)
                continue
            metadata[bulk_type] = entry
        missing = [bulk_type for bulk_type in REQUIRED_BULK_TYPES if bulk_type not in metadata]
        if missing:
            message = f"Scryfall bulk metadata is missing: {', '.join(missing)}"
            raise ValueError(message)
        self.metadata_cache.put(key, metadata)
        return metadata

    def _build_store(  # noqa: PLR0913, PLR0917
        self,
        destination: Path,
        version: str,
        card_uris: list[str],
        tags_uri: str | None,
        metadata: dict[str, BulkDataEntry],
        progress: ProgressCallback | None,
    ) -> None:
        inputs: list[Path] = []
        for bulk_type, uri in zip(REQUIRED_BULK_TYPES, card_uris, strict=True):
            inputs.append(self._download_input(bulk_type, uri, progress))
        tags_path = self._download_input(ORACLE_TAGS_TYPE, tags_uri, progress) if tags_uri is not None else None
        if progress is not None:
            progress("Building card database...", 0, 0)
        updated = [str(metadata[bulk_type].get("updated_at", "")) for bulk_type in REQUIRED_BULK_TYPES]
        if tags_uri is not None:
            updated.append(str(metadata[ORACLE_TAGS_TYPE].get("updated_at", "")))
        store.build(
            destination,
            inputs[0],
            inputs[1],
            tags_path=tags_path,
            bulk_version=version,
            built_at=max(updated, default=""),
        )
        for path in inputs:
            path.unlink(missing_ok=True)
        if tags_path is not None:
            tags_path.unlink(missing_ok=True)

    def _download_input(self, bulk_type: str, uri: str, progress: ProgressCallback | None) -> Path:
        digest = hashlib.sha256(uri.encode("utf-8")).hexdigest()[:16]
        destination = self.bulk_dir / f"{bulk_type}-{digest}.jsonl.gz"
        if destination.is_file() and _valid_gzip_jsonl(destination):
            return destination
        destination.unlink(missing_ok=True)
        label = f"Downloading {bulk_type}..."
        if progress is not None:
            progress(label, 0, 0)
        self.http.download_to_file(
            uri,
            destination,
            timeout=120,
            rate_limiter=None,
            on_progress=(None if progress is None else lambda current, total: progress(label, current, total)),
        )
        if not _valid_gzip_jsonl(destination):
            destination.unlink(missing_ok=True)
            message = f"Downloaded Scryfall bulk file is corrupt: {bulk_type}"
            raise ValueError(message)
        return destination

    def _usable_generation(self, version: str) -> Path | None:
        candidates = sorted(
            self.bulk_dir.glob(f"cards-{version}-v{store.STORE_SCHEMA_VERSION}*.db"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return next((path for path in candidates if store.validate_store(path)), None)

    def _latest_usable_generation(self) -> Path | None:
        candidates = sorted(
            self.bulk_dir.glob(f"cards-*-v{store.STORE_SCHEMA_VERSION}*.db"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return next((path for path in candidates if store.validate_store(path)), None)

    def _migrate_legacy_store(self) -> None:
        if self.legacy_cache_dir is None:
            return
        legacy_dir = self.legacy_cache_dir / "bulk"
        if not legacy_dir.is_dir():
            return
        pattern = f"cards-*-v{store.STORE_SCHEMA_VERSION}*.db"
        for source in legacy_dir.glob(pattern):
            destination = self.bulk_dir / source.name
            if destination.exists() or not store.validate_store(source):
                continue
            temporary = self.bulk_dir / f".{source.stem}-migration-{threading.get_ident()}.db"
            try:
                shutil.copy2(source, temporary)
                if store.validate_store(temporary):
                    temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)


def _valid_gzip_jsonl(path: Path) -> bool:
    try:
        first_line: str | None = None
        with gzip.open(path, "rt", encoding="utf-8") as source:
            for line in source:
                if first_line is None and line.strip():
                    first_line = line
        if first_line is None:
            return False
        return isinstance(json.loads(first_line), dict)
    except OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError:
        return False


def _validate_bulk_metadata(value: object) -> dict[str, BulkDataEntry] | None:
    if not isinstance(value, dict):
        return None
    metadata: dict[str, BulkDataEntry] = {}
    for bulk_type in REQUIRED_BULK_TYPES:
        entry = value.get(bulk_type)
        if not isinstance(entry, dict):
            return None
        uri = entry.get("jsonl_download_uri")
        if not isinstance(uri, str) or uri == "":
            return None
        metadata[bulk_type] = cast("BulkDataEntry", entry)
    tags_entry = value.get(ORACLE_TAGS_TYPE)
    if isinstance(tags_entry, dict):
        uri = tags_entry.get("jsonl_download_uri")
        if isinstance(uri, str) and uri != "":
            metadata[ORACLE_TAGS_TYPE] = cast("BulkDataEntry", tags_entry)
    return metadata


def _require_valid_store(path: Path) -> None:
    if not store.validate_store(path):
        message = f"Scryfall database generation is invalid: {path.name}"
        raise CacheError(message)
