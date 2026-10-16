from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from mtg_scripts.common.cache import (
    BytesDiskCache,
    CachePaths,
    JsonDiskCache,
    canonical_cache_key,
)

ROOT = Path(__file__).resolve().parents[2]


def test_cache_path_precedence_and_pure_resolution(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    environment = tmp_path / "environment"
    assert CachePaths.resolve(explicit, environ={"MTG_SCRIPTS_CACHE_DIR": str(environment)}).root == explicit
    assert CachePaths.resolve(environ={"MTG_SCRIPTS_CACHE_DIR": str(environment)}).root == environment
    assert CachePaths.resolve(environ={}).root == CachePaths.resolve().root
    paths = CachePaths.resolve(explicit, environ={})
    assert paths.namespace("Scryfall", "bulk") == explicit / "scryfall" / "bulk"
    assert not explicit.exists()


@pytest.mark.parametrize("component", ["..", "../escape", "a/b", ".", "", "C:\\root"])
def test_cache_namespaces_cannot_escape_root(tmp_path: Path, component: str) -> None:
    with pytest.raises(ValueError, match="namespace"):
        CachePaths.resolve(tmp_path).namespace(component, "json")


def test_canonical_key_preserves_query_literals_and_representation() -> None:
    first = canonical_cache_key("get", "https://example.test/search", params={"q": 'name:"Fire // Ice"'})
    second = canonical_cache_key("GET", "https://example.test/search", params={"q": 'name: "Fire // Ice"'})
    assert first != second
    assert first == canonical_cache_key("GET", "https://example.test/search", params={"q": 'name:"Fire // Ice"'})
    assert first != canonical_cache_key(
        "GET", "https://example.test/search", params={"q": 'name:"Fire // Ice"'}, representation={"locale": "en"}
    )


def test_json_cache_freshness_envelope_and_stale_refresh(tmp_path: Path) -> None:
    now = [1000.0]
    cache = JsonDiskCache(tmp_path / "json", clock=lambda: now[0])
    calls = 0

    def fetch() -> object:
        nonlocal calls
        calls += 1
        return {"result": calls}

    assert cache.get_or_fetch("key", fetch, max_age=10).value == {"result": 1}
    now[0] = 1009
    assert cache.get_or_fetch("key", fetch, max_age=10).value == {"result": 1}
    now[0] = 1011
    record = cache.get_or_fetch("key", fetch, max_age=10)
    assert record.value == {"result": 2}
    assert record.fetched_at == 1011
    assert calls == 2


def test_json_envelope_records_provider_fetch_time_and_freshness(tmp_path: Path) -> None:
    now = [123.0]
    cache = JsonDiskCache(tmp_path / "scryfall" / "search", provider="scryfall", clock=lambda: now[0])
    cache.get_or_fetch("key", lambda: {"cards": []}, max_age=600)
    record = cache._cache.read("key")
    assert record is not None
    assert json.loads(record.value) == {
        "version": 1,
        "provider": "scryfall",
        "fetched_at": 123,
        "max_age": 600,
        "value": {"cards": []},
    }


def test_result_specific_ttl_refreshes_negative_entry_and_preserves_it_on_failure(tmp_path: Path) -> None:
    now = [100.0]
    cache = JsonDiskCache(tmp_path / "search", clock=lambda: now[0])

    def short_negative_ttl(value: object) -> int:
        return 5 if value == {"cards": []} else 100

    cache.get_or_fetch("tag-query", lambda: {"cards": []}, max_age=100, freshness=short_negative_ttl)
    old_entry = cache._cache._path("tag-query").read_bytes()
    now[0] = 106
    assert cache.get("tag-query", max_age=100) is None
    stale = cache.get("tag-query", allow_stale=True)
    assert stale is not None
    assert stale.value == {"cards": []}
    with pytest.raises(RuntimeError, match="offline"):
        cache.get_or_fetch(
            "tag-query",
            lambda: (_ for _ in ()).throw(RuntimeError("offline")),
            max_age=100,
            freshness=short_negative_ttl,
        )
    assert cache._cache._path("tag-query").read_bytes() == old_entry
    refreshed = cache.get_or_fetch(
        "tag-query", lambda: {"cards": [{"id": "fresh"}]}, max_age=100, freshness=short_negative_ttl
    )
    assert refreshed.value == {"cards": [{"id": "fresh"}]}


def test_corrupt_or_incomplete_entries_are_refetched(tmp_path: Path) -> None:
    cache = JsonDiskCache(tmp_path / "json")
    cache.get_or_fetch("key", lambda: {"good": True})
    cache._cache._path("key").write_bytes(b"bad timestamp")
    assert cache.get_or_fetch("key", lambda: {"recovered": True}).value == {"recovered": True}
    cache._cache._path("key").write_bytes(
        (1000 * 1_000_000).to_bytes(8, "big") + (0).to_bytes(8, "big") + b'{"version":0}'
    )
    assert cache.get_or_fetch("key", lambda: {"recovered": "envelope"}).value == {"recovered": "envelope"}


def test_loader_failure_does_not_replace_stale_or_last_good_bytes(tmp_path: Path) -> None:
    now = [100.0]
    cache = JsonDiskCache(tmp_path / "json", clock=lambda: now[0])
    cache.put("key", {"last_good": True})
    existing = cache._cache._path("key").read_bytes()
    now[0] = 200
    with pytest.raises(RuntimeError, match="offline"):
        cache.get_or_fetch("key", lambda: (_ for _ in ()).throw(RuntimeError("offline")), max_age=1)
    assert cache._cache._path("key").read_bytes() == existing


def test_clear_reclaims_old_files_without_republishing_inflight(tmp_path: Path) -> None:
    cache = JsonDiskCache(tmp_path / "json")
    cache.put("cached", {"value": 1})
    previous_path = cache._cache._path("cached")
    cache.clear()
    assert not previous_path.exists()
    assert cache.get("cached") is None


def test_corrupt_epoch_fails_closed_until_cache_clear(tmp_path: Path) -> None:
    cache = JsonDiskCache(tmp_path / "json")
    cache.put("key", {"old": True})
    cache._cache._epoch_path.write_text("broken", encoding="ascii")
    assert cache.get("key") is None
    with pytest.raises(RuntimeError, match="epoch is corrupt"):
        cache.get_or_fetch("key", lambda: {"fresh": True})
    cache.clear()
    assert cache.get_or_fetch("key", lambda: {"fresh": True}).value == {"fresh": True}
    started = threading.Event()
    resume = threading.Event()
    returned: list[object] = []

    def fetch() -> object:
        started.set()
        assert resume.wait(5)
        return {"after_clear": True}

    worker = threading.Thread(target=lambda: returned.append(cache.get_or_fetch("inflight", fetch).value))
    worker.start()
    assert started.wait(5)
    cache.clear()
    resume.set()
    worker.join(5)
    assert not worker.is_alive()
    assert returned == [{"after_clear": True}]
    assert cache.get("inflight") is None


def test_legacy_json_import_is_marked_stale_and_source_is_kept(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.json"
    legacy.write_text('{"legacy":true}', encoding="utf-8")
    now = [10.0]
    cache = JsonDiskCache(tmp_path / "json", clock=lambda: now[0])
    assert cache.import_legacy("key", legacy)
    assert cache.get("key", max_age=5) is None
    imported = cache.get("key")
    assert imported is not None
    assert imported.value == {"legacy": True}
    assert legacy.read_text(encoding="utf-8") == '{"legacy":true}'


def test_byte_cache_is_shared_between_instances_and_clear_is_scoped(tmp_path: Path) -> None:
    first = BytesDiskCache(tmp_path / "scryfall" / "images")
    second = BytesDiskCache(tmp_path / "scryfall" / "images")
    calls = 0

    def fetch() -> bytes:
        nonlocal calls
        calls += 1
        return b"image-payload"

    assert first.get_or_fetch("image-key", fetch) == b"image-payload"
    assert second.get_or_fetch("image-key", fetch) == b"image-payload"
    assert calls == 1
    first.clear()
    assert second.get("image-key") is None
    other_provider = BytesDiskCache(tmp_path / "riftcodex" / "images")
    other_provider.put("image-key", b"other")
    first.clear()
    assert other_provider.get("image-key") == b"other"


def test_two_processes_share_one_fetch_per_key(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    marker = tmp_path / "fetch.marker"
    script = r"""
import sys
import time
from pathlib import Path
from mtg_scripts.common.cache import JsonDiskCache
directory = Path(sys.argv[1])
marker = Path(sys.argv[2])
def fetch():
    marker.write_text("fetched", encoding="utf-8")
    time.sleep(0.3)
    return {"value": 7}
record = JsonDiskCache(directory).get_or_fetch("same", fetch)
assert record.value == {"value": 7}
"""
    environment = os.environ | {"PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    command = [sys.executable, "-B", "-c", script, str(cache_dir), str(marker)]
    first = subprocess.Popen(  # noqa: S603
        command, cwd=tmp_path, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    second = subprocess.Popen(  # noqa: S603
        command, cwd=tmp_path, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    first_output = first.communicate(timeout=15)
    second_output = second.communicate(timeout=15)
    assert first.returncode == second.returncode == 0, first_output[1] + second_output[1]
    assert marker.read_text(encoding="utf-8") == "fetched"
    assert len(list(cache_dir.glob("*.cache"))) == 1
