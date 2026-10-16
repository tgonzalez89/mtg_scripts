from __future__ import annotations

import random
import threading
import time
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import TYPE_CHECKING, cast, override

import pytest
import requests

from mtg_scripts.common.cache import BytesDiskCache, JsonDiskCache
from mtg_scripts.common.http import DiskRateLimiter, HttpRequestError, JsonHttpClient

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from pathlib import Path


class _Response:
    def __init__(
        self, status: int, *, payload: object = None, content: bytes = b"", headers: Mapping[str, str] | None = None
    ) -> None:
        self.status_code = status
        self.payload = payload
        self.content = content
        self.headers = dict(headers or {})
        self.closed = False

    def json(self) -> object:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            message = f"HTTP {self.status_code}"
            raise requests.HTTPError(message)

    def close(self) -> None:
        self.closed = True


class _Session:
    def __init__(self, responses: list[_Response | Exception]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.closed = False
        self._lock = threading.Lock()

    def request(self, method: str, url: str, **kwargs: object) -> _Response:
        with self._lock:
            self.calls.append((method, url, kwargs))
            result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self) -> None:
        self.closed = True


class _StreamingResponse(_Response):
    def __init__(self, chunks: list[bytes | Exception], *, headers: Mapping[str, str] | None = None) -> None:
        super().__init__(200, headers=headers)
        self.chunks = chunks

    def iter_content(self, *, chunk_size: int) -> Iterator[bytes]:
        assert chunk_size > 0
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


def _client(  # noqa: PLR0913
    session: _Session,
    *,
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
) -> JsonHttpClient:
    return JsonHttpClient(
        session=cast("requests.Session", session),
        user_agent="test-agent",
        timeout=timeout,
        retries=retries,
        base_delay=base_delay,
        max_delay=max_delay,
        jitter=jitter,
        clock=clock,
        sleep=sleep,
        random_uniform=random_uniform,
        rate_limiter=rate_limiter,
        json_cache=json_cache,
        bytes_cache=bytes_cache,
        json_max_age=json_max_age,
    )


def test_get_retries_429_honors_retry_after_and_closes_response() -> None:
    limited = _Response(429, headers={"Retry-After": "1.5"})
    success = _Response(200, payload={"ok": True})
    session = _Session([limited, success])
    sleeps: list[float] = []
    client = _client(session, retries=2, base_delay=0.5, max_delay=3, jitter=0, sleep=sleeps.append)
    assert client.get_json("https://example.test/cards") == {"ok": True}
    assert sleeps == [1.5]
    assert limited.closed
    assert success.closed
    assert [call[0] for call in session.calls] == ["GET", "GET"]
    assert all(call[2]["timeout"] == 20 for call in session.calls)
    assert session.headers == {"User-Agent": "test-agent"}
    client.close()
    assert not session.closed


def test_get_retries_transient_transport_errors_with_bounded_backoff() -> None:
    session = _Session([requests.Timeout("slow"), _Response(200, payload=[1])])
    sleeps: list[float] = []
    client = _client(
        session,
        retries=2,
        base_delay=1,
        max_delay=2,
        jitter=0.2,
        random_uniform=lambda low, high: high,
        sleep=sleeps.append,
    )
    assert client.get_json("https://example.test/cards") == [1]
    assert sleeps == [1.2]
    assert len(session.calls) == 2


def test_retry_exhaustion_is_normalized_and_final_response_closed() -> None:
    first = _Response(503)
    final = _Response(503)
    session = _Session([first, final])
    client = _client(session, retries=1, jitter=0, sleep=lambda _: None)
    with pytest.raises(HttpRequestError, match="HTTP 503"):
        client.get_json("https://example.test/cards")
    assert first.closed
    assert final.closed
    assert len(session.calls) == 2


def test_post_is_not_retried() -> None:
    response = _Response(429, headers={"Retry-After": "0"})
    session = _Session([response, _Response(200, payload={"must_not": "happen"})])
    client = _client(session, retries=5, sleep=lambda _: pytest.fail("POST retried"))
    with pytest.raises(HttpRequestError, match="HTTP 429"):
        client.post_json("https://example.test/mutate", payload={"value": 1})
    assert len(session.calls) == 1
    assert response.closed


def test_malformed_json_is_an_http_error_and_response_is_closed() -> None:
    class MalformedResponse(_Response):
        @override
        def json(self) -> object:
            message = "bad json"
            raise ValueError(message)

    response = MalformedResponse(200)
    client = _client(_Session([response]))
    with pytest.raises(HttpRequestError, match="Invalid JSON"):
        client.get_json("https://example.test/cards")
    assert response.closed


def test_json_cache_keys_query_params_and_expires_by_policy(tmp_path: Path) -> None:
    now = [100.0]
    session = _Session([_Response(200, payload={"q": "first"}), _Response(200, payload={"q": "second"})])
    cache = JsonDiskCache(tmp_path / "search", clock=lambda: now[0])
    client = _client(session, json_cache=cache, json_max_age=10)
    first = 'name:"Fire // Ice"'
    assert client.get_json("https://example.test/search", params={"q": first}) == {"q": "first"}
    assert client.get_json("https://example.test/search", params={"q": first}) == {"q": "first"}
    assert client.get_json("https://example.test/search", params={"q": 'name: "Fire // Ice"'}) == {"q": "second"}
    assert len(session.calls) == 2


def test_cache_expiry_retries_and_refreshes(tmp_path: Path) -> None:
    now = [100.0]
    session = _Session([_Response(200, payload=1), _Response(200, payload=2)])
    client = _client(
        session,
        json_cache=JsonDiskCache(tmp_path / "json", clock=lambda: now[0]),
        json_max_age=10,
    )
    assert client.get_json("https://example.test/data") == 1
    now[0] = 111
    assert client.get_json("https://example.test/data") == 2
    assert len(session.calls) == 2


def test_byte_cache_returns_exact_response_content(tmp_path: Path) -> None:
    session = _Session([_Response(200, content=b"image-bytes")])
    cache = BytesDiskCache(tmp_path / "images")
    client = _client(session, bytes_cache=cache)
    assert client.get_bytes("https://example.test/card.png") == b"image-bytes"
    assert client.get_bytes("https://example.test/card.png") == b"image-bytes"
    assert len(session.calls) == 1


def test_rate_limiter_waits_and_persists_minimum_interval(tmp_path: Path) -> None:
    now = [100.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = DiskRateLimiter(tmp_path / "rate.lock", min_interval=0.1, clock=lambda: now[0], sleep=sleep)
    limiter.wait()
    limiter.wait()
    assert sleeps == pytest.approx([0.1])
    assert float(limiter.state_path.read_text(encoding="ascii")) == pytest.approx(100.1)


def test_rate_limiter_rejects_negative_interval(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="min_interval"):
        DiskRateLimiter(tmp_path / "rate.lock", min_interval=-1)


def test_separate_rate_limiter_instances_share_clock_state(tmp_path: Path) -> None:
    now = [20.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    path = tmp_path / "api.lock"
    DiskRateLimiter(path, min_interval=0.25, clock=lambda: now[0], sleep=sleep).wait()
    DiskRateLimiter(path, min_interval=0.25, clock=lambda: now[0], sleep=sleep).wait()
    assert sleeps == pytest.approx([0.25])


def test_retry_after_http_date_is_parsed_and_capped() -> None:
    now = 1_700_000_000.0
    session = _Session(
        [
            _Response(429, headers={"Retry-After": format_datetime(datetime.fromtimestamp(now + 10, UTC))}),
            _Response(200, payload={"ok": True}),
        ]
    )
    sleeps: list[float] = []
    client = _client(session, retries=1, max_delay=2, jitter=0, clock=lambda: now, sleep=sleeps.append)
    assert client.get_json("https://example.test/cards") == {"ok": True}
    assert sleeps == [2]


def test_stream_download_retries_interrupted_body_and_replaces_atomically(tmp_path: Path) -> None:
    destination = tmp_path / "bulk.jsonl.gz"
    destination.write_bytes(b"last-known-good")
    broken = _StreamingResponse([b"partial", requests.ConnectionError("stream broke")])
    complete = _StreamingResponse([b"new-", b"complete"], headers={"content-length": "12"})
    client = _client(_Session([broken, complete]), retries=1, jitter=0, sleep=lambda _: None)
    progress: list[tuple[int, int]] = []

    downloaded = client.download_to_file(
        "https://example.test/bulk.gz",
        destination,
        chunk_size=4,
        on_progress=lambda current, total: progress.append((current, total)),
    )

    assert downloaded == 12
    assert destination.read_bytes() == b"new-complete"
    assert progress == [(7, 0), (4, 12), (12, 12)]
    assert broken.closed
    assert complete.closed
    assert list(tmp_path.iterdir()) == [destination]


def test_stream_failure_keeps_existing_file_and_removes_temporary(tmp_path: Path) -> None:
    destination = tmp_path / "bulk.gz"
    destination.write_bytes(b"last-good")
    response = _StreamingResponse([b"partial", requests.ConnectionError("interrupted")])
    client = _client(_Session([response]), retries=0)
    with pytest.raises(HttpRequestError, match="interrupted while downloading"):
        client.download_to_file("https://example.test/bulk.gz", destination)
    assert destination.read_bytes() == b"last-good"
    assert response.closed
    assert list(tmp_path.iterdir()) == [destination]


def test_client_closes_only_a_session_it_owns() -> None:
    injected = _Session([])
    _client(injected).close()
    assert not injected.closed

    owned = JsonHttpClient(user_agent="test-agent")
    session = owned.session
    owned.close()
    assert session is not None
