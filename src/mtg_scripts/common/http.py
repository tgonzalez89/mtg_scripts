"""Provider-configurable HTTP requests, retries, throttling, and optional caches."""

from __future__ import annotations

import email.utils
import math
import os
import random
import tempfile
import threading
import time
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, cast

import requests
from filelock import FileLock

from .cache import BytesDiskCache, CacheRecord, JsonDiskCache, canonical_cache_key

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from requests import Response

_USE_DEFAULT_LIMITER = object()

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class HttpRequestError(RuntimeError):
    """A bounded HTTP request failed, or its response was not valid JSON."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DiskRateLimiter:
    """Coordinate a minimum request interval across processes sharing a lock path."""

    def __init__(
        self,
        lock_path: str | Path,
        *,
        min_interval: float,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not math.isfinite(min_interval) or min_interval < 0:
            message = "min_interval must be finite and non-negative."
            raise ValueError(message)
        self.lock_path = Path(lock_path)
        self.state_path = self.lock_path.with_suffix(self.lock_path.suffix + ".state")
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep

    def wait(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.lock_path)):
            try:
                previous = float(self.state_path.read_text(encoding="ascii"))
            except FileNotFoundError, ValueError:
                previous = 0.0
            now = self._clock()
            delay = max(0.0, previous + self.min_interval - now)
            if delay:
                self._sleep(delay)
                now = self._clock()
            descriptor, temporary_name = tempfile.mkstemp(dir=self.state_path.parent, prefix=".rate.", suffix=".tmp")
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w", encoding="ascii") as output:
                    output.write(f"{now:.9f}")
                temporary.replace(self.state_path)
            finally:
                temporary.unlink(missing_ok=True)


class JsonHttpClient:
    """A serialized requests session with GET retries and optional disk caches."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        session: requests.Session | None = None,
        user_agent: str,
        timeout: float = 20,
        retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 8,
        jitter: float = 0.25,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
        rate_limiter: DiskRateLimiter | None = None,
        json_cache: JsonDiskCache | None = None,
        bytes_cache: BytesDiskCache | None = None,
        json_max_age: float | None = None,
    ) -> None:
        if (
            retries < 0
            or not all(math.isfinite(value) for value in (timeout, base_delay, max_delay, jitter))
            or timeout <= 0
            or base_delay < 0
            or max_delay < 0
            or jitter < 0
        ):
            message = "HTTP timeout and retry settings must be non-negative; timeout must be positive."
            raise ValueError(message)
        self.session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self.session.headers.update({"User-Agent": user_agent})
        self.timeout = timeout
        self.retries = retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self._clock = clock
        self._sleep = sleep
        self._random_uniform = random_uniform
        self.rate_limiter = rate_limiter
        self.json_cache = json_cache
        self.bytes_cache = bytes_cache
        self.json_max_age = json_max_age
        self._session_lock = threading.Lock()

    def close(self) -> None:
        if self._owns_session:
            self.session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_json(  # noqa: PLR0913
        self,
        url: str,
        *,
        params: Mapping[str, str | int | float | bool | None] | None = None,
        max_age: float | None = None,
        representation: object = None,
        use_cache: bool = True,
        rate_limiter: DiskRateLimiter | object | None = _USE_DEFAULT_LIMITER,
    ) -> object:
        key = canonical_cache_key("GET", url, params=params, representation=representation)
        cache = self.json_cache
        age = self.json_max_age if max_age is None else max_age
        if cache is None or not use_cache:
            return self._get_json(url, params, rate_limiter=rate_limiter)
        record: CacheRecord[object] = cache.get_or_fetch(
            key, lambda: self._get_json(url, params, rate_limiter=rate_limiter), max_age=age
        )
        return record.value

    def get_bytes(
        self,
        url: str,
        *,
        params: Mapping[str, str | int | float | bool | None] | None = None,
        representation: object = None,
        rate_limiter: DiskRateLimiter | object | None = _USE_DEFAULT_LIMITER,
    ) -> bytes:
        key = canonical_cache_key("GET", url, params=params, representation=representation)
        if self.bytes_cache is None:
            return self._get_bytes(url, params, rate_limiter=rate_limiter)
        return self.bytes_cache.get_or_fetch(key, lambda: self._get_bytes(url, params, rate_limiter=rate_limiter))

    def post_json(self, url: str, *, payload: Mapping[str, object]) -> object:
        key = canonical_cache_key("POST", url, payload=payload)
        if self.json_cache is not None:
            record = self.json_cache.get_or_fetch(key, lambda: self._post_json(url, payload), max_age=self.json_max_age)
            return record.value
        return self._post_json(url, payload)

    def _post_json(self, url: str, payload: Mapping[str, object]) -> object:
        response = self._request("POST", url, json_payload=payload, retryable=False)
        try:
            return response.json()
        except (ValueError, requests.RequestException) as error:
            message = f"Invalid JSON response from POST {url}: {error}"
            raise HttpRequestError(message) from error
        finally:
            response.close()

    def _get_json(
        self,
        url: str,
        params: Mapping[str, str | int | float | bool | None] | None,
        *,
        rate_limiter: DiskRateLimiter | object | None = _USE_DEFAULT_LIMITER,
    ) -> object:
        response = self._request("GET", url, params=params, retryable=True, rate_limiter=rate_limiter)
        try:
            return response.json()
        except (ValueError, requests.RequestException) as error:
            message = f"Invalid JSON response from GET {url}: {error}"
            raise HttpRequestError(message) from error
        finally:
            response.close()

    def _get_bytes(
        self,
        url: str,
        params: Mapping[str, str | int | float | bool | None] | None,
        *,
        rate_limiter: DiskRateLimiter | object | None = _USE_DEFAULT_LIMITER,
    ) -> bytes:
        response = self._request("GET", url, params=params, retryable=True, rate_limiter=rate_limiter)
        try:
            return response.content
        finally:
            response.close()

    def download_to_file(  # noqa: PLR0913
        self,
        url: str,
        destination: str | Path,
        *,
        chunk_size: int = 1024 * 1024,
        timeout: float | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        rate_limiter: DiskRateLimiter | object | None = _USE_DEFAULT_LIMITER,
    ) -> int:
        """Stream a GET into an atomically published file; retry interrupted bodies."""
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(self.retries + 1):
            response = self._request(
                "GET", url, retryable=True, stream=True, timeout=timeout, rate_limiter=rate_limiter
            )
            descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
            temporary = Path(temporary_name)
            try:
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with os.fdopen(descriptor, "wb") as output:
                    if hasattr(response, "iter_content"):
                        chunks = response.iter_content(chunk_size=chunk_size)
                    else:
                        chunks = (response.content,)
                    for chunk in chunks:
                        if chunk:
                            output.write(chunk)
                            downloaded += len(chunk)
                            if on_progress is not None:
                                on_progress(downloaded, total)
                temporary.replace(path)
            except requests.RequestException as error:
                if attempt == self.retries:
                    message = f"GET {url} interrupted while downloading: {error}"
                    raise HttpRequestError(message) from error
                self._sleep(self._retry_delay(attempt, None))
            else:
                return downloaded
            finally:
                response.close()
                temporary.unlink(missing_ok=True)
        message = "HTTP download retry loop exited unexpectedly."
        raise AssertionError(message)

    def _request(  # noqa: PLR0913
        self,
        method: str,
        url: str,
        *,
        retryable: bool,
        timeout: float | None = None,
        rate_limiter: DiskRateLimiter | object | None = _USE_DEFAULT_LIMITER,
        params: Mapping[str, str | int | float | bool | None] | None = None,
        json_payload: Mapping[str, object] | None = None,
        stream: bool = False,
    ) -> Response:
        max_attempts = self.retries + 1 if retryable else 1
        for attempt in range(max_attempts):
            limiter = self.rate_limiter if rate_limiter is _USE_DEFAULT_LIMITER else rate_limiter
            if limiter is not None:
                cast("DiskRateLimiter", limiter).wait()
            try:
                with self._session_lock:
                    response = self.session.request(
                        method,
                        url,
                        timeout=self.timeout if timeout is None else timeout,
                        params=params,
                        json=cast("Any", json_payload),
                        stream=stream,
                    )
            except requests.RequestException as error:
                if not retryable or attempt + 1 == max_attempts:
                    message = f"{method} {url} failed: {error}"
                    raise HttpRequestError(message) from error
                self._sleep(self._retry_delay(attempt, None))
                continue

            if response.status_code in RETRYABLE_STATUS_CODES and attempt + 1 < max_attempts:
                retry_after = _retry_after_seconds(response.headers.get("Retry-After"), self._clock())
                response.close()
                self._sleep(self._retry_delay(attempt, retry_after))
                continue
            try:
                response.raise_for_status()
            except requests.RequestException as error:
                response.close()
                message = f"{method} {url} returned HTTP {response.status_code}: {error}"
                raise HttpRequestError(message, status_code=response.status_code) from error
            else:
                return response
        message = "HTTP retry loop exited unexpectedly."
        raise AssertionError(message)

    def _retry_delay(self, attempt: int, retry_after: float | None) -> float:
        backoff = min(self.base_delay * 2**attempt, self.max_delay)
        delay = min(self.max_delay, backoff + self._random_uniform(0, self.jitter))
        if retry_after is not None:
            delay = min(self.max_delay, max(delay, retry_after))
        return float(delay)


def _retry_after_seconds(value: str | None, now: float) -> float | None:
    if value is None or value == "":
        return None
    try:
        seconds = float(value)
        return max(0.0, seconds) if math.isfinite(seconds) else None
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
        except TypeError, ValueError, OverflowError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return max(0.0, parsed.timestamp() - now)
