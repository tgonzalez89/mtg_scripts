"""Namespaced per-user cache paths and process-safe atomic file caches."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from filelock import FileLock
from platformdirs import user_cache_path

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

CACHE_DIR_ENV: Final = "MTG_SCRIPTS_CACHE_DIR"
CACHE_ENVELOPE_VERSION: Final = 1
_TIMESTAMP_BYTES: Final = 8
_EPOCH_BYTES: Final = 8


class CacheError(RuntimeError):
    """A cache entry could not be read or validated."""


@dataclass(frozen=True, slots=True)
class CachePaths:
    """Resolve paths without creating any directories."""

    root: Path

    @classmethod
    def resolve(
        cls,
        cache_dir: str | Path | None = None,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> CachePaths:
        if cache_dir is not None:
            return cls(Path(cache_dir).expanduser())
        variables = os.environ if environ is None else environ
        configured = variables.get(CACHE_DIR_ENV)
        if configured is not None and configured != "":
            return cls(Path(configured).expanduser())
        return cls(Path(user_cache_path("mtg-scripts")))

    def namespace(self, provider: str, category: str) -> Path:
        return self.root / _validate_component(provider) / _validate_component(category)


def _validate_component(component: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", component):
        message = f"Invalid cache namespace component: {component!r}"
        raise ValueError(message)
    return component.lower()


def canonical_cache_key(
    method: str,
    url: str,
    *,
    params: object = None,
    payload: object = None,
    representation: object = None,
) -> str:
    """Build a stable key without normalizing arbitrary URL/query text."""
    return json.dumps(
        {
            "method": method.upper(),
            "url": url,
            "params": params,
            "payload": payload,
            "representation": representation,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


@dataclass(frozen=True, slots=True)
class CacheRecord[T]:
    value: T
    fetched_at: float


class _AtomicFileCache:
    def __init__(self, directory: str | Path, *, clock: Callable[[], float] = time.time) -> None:
        self.directory = Path(directory)
        self._clock = clock
        self._inflight_lock = threading.Lock()
        self._inflight: dict[str, Future[Any]] = {}
        self._epoch_path = self.directory / ".epoch"
        self._clear_lock_path = self.directory / ".clear.lock"
        self._locks_dir = self.directory / ".locks"

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.cache"

    def _key_lock(self, key: str) -> FileLock:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._lock_for_digest(digest)

    def _lock_for_digest(self, digest: str) -> FileLock:
        return FileLock(str(self._locks_dir / f"{digest}.lock"))

    def _epoch(self) -> str:
        try:
            value = self._epoch_path.read_text(encoding="ascii")
        except FileNotFoundError:
            return "0"
        try:
            epoch = int(value)
        except ValueError:
            return "-1"
        return str(epoch) if epoch >= 0 else "invalid"

    def _read_path(self, path: Path, max_age: float | None) -> CacheRecord[bytes] | None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        if len(data) < _TIMESTAMP_BYTES + _EPOCH_BYTES:
            return None
        fetched_at = int.from_bytes(data[:_TIMESTAMP_BYTES], byteorder="big") / 1_000_000
        entry_epoch = int.from_bytes(data[_TIMESTAMP_BYTES : _TIMESTAMP_BYTES + _EPOCH_BYTES], byteorder="big")
        now = self._clock()
        if (
            not math.isfinite(fetched_at)
            or fetched_at < 0
            or fetched_at > now
            or (max_age is not None and now - fetched_at > max_age)
            or entry_epoch != int(self._epoch())
        ):
            return None
        return CacheRecord(value=data[_TIMESTAMP_BYTES + _EPOCH_BYTES :], fetched_at=fetched_at)

    def _publish(self, path: Path, value: bytes, fetched_at: float, expected_epoch: str) -> bool:
        if not expected_epoch.isdigit():
            message = "Cache invalidation epoch is corrupt; clear the cache to recover it."
            raise CacheError(message)
        if not math.isfinite(fetched_at) or fetched_at < 0:
            message = "Cache timestamps must be finite non-negative values."
            raise ValueError(message)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._locks_dir.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self._clear_lock_path)):
            if self._epoch() != expected_epoch:
                return False
            descriptor, temporary_name = tempfile.mkstemp(dir=self.directory, prefix=f".{path.name}.", suffix=".tmp")
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(int(fetched_at * 1_000_000).to_bytes(_TIMESTAMP_BYTES, byteorder="big"))
                    output.write(int(expected_epoch).to_bytes(_EPOCH_BYTES, byteorder="big"))
                    output.write(value)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        return True

    def _coalesce[T](self, key: str, factory: Callable[[], T]) -> T:
        with self._inflight_lock:
            pending = self._inflight.get(key)
            future: Future[T] = Future() if pending is None else cast("Future[T]", pending)
            if pending is None:
                self._inflight[key] = cast("Future[Any]", future)
        if pending is not None:
            return future.result()
        try:
            result = factory()
        except BaseException as error:
            future.set_exception(error)
            raise
        else:
            future.set_result(result)
            return result
        finally:
            with self._inflight_lock:
                self._inflight.pop(key, None)

    def get_or_fetch(
        self,
        key: str,
        fetch: Callable[[], bytes],
        *,
        max_age: float | None = None,
        validate: Callable[[bytes], bool] | None = None,
    ) -> CacheRecord[bytes]:
        if max_age is not None and (not math.isfinite(max_age) or max_age < 0):
            message = "Cache max_age must be non-negative or None."
            raise ValueError(message)
        path = self._path(key)

        def load() -> CacheRecord[bytes]:
            record = self._read_path(path, max_age)
            if record is not None and (validate is None or validate(record.value)):
                return record
            expected_epoch = self._epoch()
            self.directory.mkdir(parents=True, exist_ok=True)
            self._locks_dir.mkdir(parents=True, exist_ok=True)
            with self._key_lock(key):
                record = self._read_path(path, max_age)
                if record is not None and (validate is None or validate(record.value)):
                    return record
                value = fetch()
                fetched_at = self._clock()
                self._publish(path, value, fetched_at, expected_epoch)
                return CacheRecord(value=value, fetched_at=fetched_at)

        return self._coalesce(key, load)

    def read(self, key: str, *, max_age: float | None = None) -> CacheRecord[bytes] | None:
        return self._read_path(self._path(key), max_age)

    def put(self, key: str, value: bytes, *, fetched_at: float | None = None) -> None:
        expected_epoch = self._epoch()
        path = self._path(key)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._locks_dir.mkdir(parents=True, exist_ok=True)
        with self._key_lock(key):
            self._publish(path, value, self._clock() if fetched_at is None else fetched_at, expected_epoch)

    def put_if_absent(self, key: str, value: bytes, *, fetched_at: float) -> bool:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._locks_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        with self._key_lock(key):
            if self._read_path(path, None) is not None:
                return False
            expected_epoch = self._epoch()
            return self._publish(path, value, fetched_at, expected_epoch)

    def discard(self, key: str) -> None:
        self._locks_dir.mkdir(parents=True, exist_ok=True)
        with self._key_lock(key):
            self._path(key).unlink(missing_ok=True)

    def clear(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._locks_dir.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self._clear_lock_path)):
            try:
                epoch = int(self._epoch())
            except ValueError:
                epoch = 0
            new_epoch = str(max(0, epoch) + 1)
            self._write_epoch(new_epoch)
        for cache_file in self.directory.glob("*.cache"):
            digest = cache_file.stem
            with self._lock_for_digest(digest), FileLock(str(self._clear_lock_path)):
                if self._epoch() != new_epoch:
                    return
                try:
                    header = cache_file.read_bytes()[: _TIMESTAMP_BYTES + _EPOCH_BYTES]
                    entry_epoch = int.from_bytes(header[_TIMESTAMP_BYTES:], byteorder="big")
                except OSError:
                    continue
                if len(header) < _TIMESTAMP_BYTES + _EPOCH_BYTES or entry_epoch != int(new_epoch):
                    cache_file.unlink(missing_ok=True)

    def _write_epoch(self, value: str) -> None:
        descriptor, temporary_name = tempfile.mkstemp(dir=self.directory, prefix=".epoch.", suffix=".tmp")
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="ascii") as output:
                output.write(value)
            temporary.replace(self._epoch_path)
        finally:
            temporary.unlink(missing_ok=True)


class BytesDiskCache:
    """Cross-process cache for immutable bytes such as image downloads."""

    def __init__(self, directory: str | Path, *, clock: Callable[[], float] = time.time) -> None:
        self._cache = _AtomicFileCache(directory, clock=clock)

    def get_or_fetch(
        self, key: str, fetch: Callable[[], bytes], *, validate: Callable[[bytes], bool] | None = None
    ) -> bytes:
        return self._cache.get_or_fetch(key, fetch, validate=validate).value

    def get(self, key: str) -> bytes | None:
        record = self._cache.read(key)
        return None if record is None else record.value

    def put(self, key: str, value: bytes, *, fetched_at: float | None = None) -> None:
        self._cache.put(key, value, fetched_at=fetched_at)

    def put_if_absent(self, key: str, value: bytes, *, fetched_at: float) -> bool:
        return self._cache.put_if_absent(key, value, fetched_at=fetched_at)

    def discard(self, key: str) -> None:
        self._cache.discard(key)

    def clear(self) -> None:
        self._cache.clear()


class JsonDiskCache:
    """Cross-process JSON cache with versioned freshness envelopes."""

    def __init__(
        self,
        directory: str | Path,
        *,
        provider: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._cache = _AtomicFileCache(directory, clock=clock)
        self.provider = provider
        self._clock = clock

    def _decode(self, data: bytes) -> object:
        envelope = json.loads(data)
        fetched_at = envelope.get("fetched_at") if isinstance(envelope, dict) else None
        max_age = envelope.get("max_age") if isinstance(envelope, dict) else None
        if (
            not isinstance(envelope, dict)
            or envelope.get("version") != CACHE_ENVELOPE_VERSION
            or "value" not in envelope
            or not isinstance(fetched_at, (int, float))
            or not math.isfinite(fetched_at)
            or (
                max_age is not None
                and (not isinstance(max_age, (int, float)) or not math.isfinite(max_age) or max_age < 0)
            )
            or (self.provider is not None and envelope.get("provider") != self.provider)
        ):
            message = "Invalid or unsupported JSON cache envelope."
            raise CacheError(message)
        return envelope["value"]

    def _encode(self, value: object, *, fetched_at: float, max_age: float | None) -> bytes:
        try:
            return json.dumps(
                {
                    "version": CACHE_ENVELOPE_VERSION,
                    "provider": self.provider,
                    "fetched_at": fetched_at,
                    "max_age": max_age,
                    "value": value,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            message = f"Value cannot be cached as JSON: {error}"
            raise CacheError(message) from error

    def get_or_fetch(
        self,
        key: str,
        fetch: Callable[[], object],
        *,
        max_age: float | None = None,
        freshness: Callable[[object], float | None] | None = None,
    ) -> CacheRecord[object]:
        def decode(data: bytes) -> bool:
            try:
                value = self._decode(data)
            except CacheError, UnicodeDecodeError, json.JSONDecodeError:
                return False
            age = self._declared_max_age(data) if freshness is None else freshness(value)
            if age is not None:
                envelope = json.loads(data)
                fetched_at = float(envelope["fetched_at"])
                if self._clock() - fetched_at > age:
                    return False
            return True

        def fetch_envelope() -> bytes:
            value = fetch()
            age = max_age if freshness is None else freshness(value)
            return self._encode(value, fetched_at=self._clock(), max_age=age)

        record = self._cache.get_or_fetch(key, fetch_envelope, max_age=max_age, validate=decode)
        try:
            value = self._decode(record.value)
        except (CacheError, UnicodeDecodeError, json.JSONDecodeError) as error:
            message = "Cached JSON became invalid after publication."
            raise CacheError(message) from error
        return CacheRecord(value=value, fetched_at=record.fetched_at)

    def get(
        self,
        key: str,
        *,
        max_age: float | None = None,
        allow_stale: bool = False,
    ) -> CacheRecord[object] | None:
        record = self._cache.read(key, max_age=None if allow_stale else max_age)
        if record is None:
            return None
        try:
            value = self._decode(record.value)
            declared_age = self._declared_max_age(record.value)
        except CacheError, UnicodeDecodeError, json.JSONDecodeError:
            return None
        if not allow_stale:
            effective_age = (
                declared_age if max_age is None else (max_age if declared_age is None else min(max_age, declared_age))
            )
            if effective_age is not None and self._clock() - record.fetched_at > effective_age:
                return None
        return CacheRecord(value=value, fetched_at=record.fetched_at)

    def _declared_max_age(self, data: bytes) -> float | None:
        envelope = json.loads(data)
        value = envelope["max_age"]
        return None if value is None else float(value)

    def put(
        self,
        key: str,
        value: object,
        *,
        fetched_at: float | None = None,
        max_age: float | None = None,
    ) -> None:
        timestamp = self._clock() if fetched_at is None else fetched_at
        self._cache.put(
            key,
            self._encode(value, fetched_at=timestamp, max_age=max_age),
            fetched_at=timestamp,
        )

    def import_legacy(
        self,
        key: str,
        path: str | Path,
        *,
        fetched_at: float = 0,
        fresh_for_seconds: float | None = None,
    ) -> bool:
        """Import known raw JSON as stale data; never discard the source file."""
        legacy_path = Path(path)
        try:
            with legacy_path.open(encoding="utf-8") as source:
                value = json.load(source)
        except OSError, ValueError, UnicodeDecodeError:
            return False
        return self._cache.put_if_absent(
            key,
            self._encode(value, fetched_at=fetched_at, max_age=fresh_for_seconds),
            fetched_at=fetched_at,
        )

    def clear(self) -> None:
        self._cache.clear()

    def discard(self, key: str) -> None:
        self._cache.discard(key)
