from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
import requests
from PIL import Image

from mtg_scripts.common.cache import canonical_cache_key
from mtg_scripts.print_picker.riftcodex_backend import RiftCodexBackend
from mtg_scripts.print_picker.scryfall_backend import ScryfallBackend
from mtg_scripts.services.scryfall import store as scryfall_store
from mtg_scripts.services.scryfall.bulk import BULK_DATA_URL

ORACLE_URI = "https://data.scryfall.io/oracle-cards/oracle-v1.jsonl.gz"
DEFAULT_URI = "https://data.scryfall.io/default-cards/default-v1.jsonl.gz"
ROOT = Path(__file__).resolve().parents[2]


class _Response:
    status_code = 200

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.content = payload if isinstance(payload, bytes) else b""
        self.closed = False
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload

    def close(self) -> None:
        self.closed = True


class _Session:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = payloads
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    def request(self, method: str, url: str, **_kwargs: object) -> _Response:
        self.calls.append((method, url))
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return _Response(payload)

    def close(self) -> None:
        self.closed = True


def _session(payloads: list[object]) -> requests.Session:
    return cast("requests.Session", _Session(payloads))


def _card() -> dict[str, Any]:
    return {
        "id": "fixture-print",
        "name": "Sol Ring",
        "set": "cmm",
        "set_name": "Commander Masters",
        "collector_number": "1",
        "finishes": ["nonfoil"],
        "oracle_id": "fixture-oracle",
        "released_at": "2023-08-04",
        "set_type": "masters",
        "games": ["paper"],
        "image_uris": {"normal": "https://example.test/sol-ring.png", "png": "https://example.test/sol-ring-hi.png"},
    }


def _metadata() -> dict[str, dict[str, str]]:
    return {
        "oracle_cards": {"jsonl_download_uri": ORACLE_URI},
        "default_cards": {"jsonl_download_uri": DEFAULT_URI},
    }


def _seed_store(directory: Path, cards: list[dict[str, Any]]) -> Path:
    metadata = _metadata()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    version = hashlib.sha256(f"{ORACLE_URI}\n{DEFAULT_URI}".encode()).hexdigest()[:16]
    path = scryfall_store.store_path(directory, version)
    scryfall_store.build_from_cards(path, cards)
    return path


def test_provider_namespaces_isolate_same_request_and_legacy_json_is_refreshed(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    legacy_json = legacy / "json"
    legacy_json.mkdir(parents=True)
    url = "https://api.riftcodex.com/cards/name?exact=Sol+Ring"
    legacy_path = legacy_json / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
    legacy_path.write_text('{"items":[{"name":"Old"}]}', encoding="utf-8")
    session = _Session([{"items": [{"name": "Fresh"}]}])
    rift = RiftCodexBackend(cache_dir=tmp_path / "shared", session=cast("requests.Session", session))
    rift.legacy_cache_dir = legacy

    assert rift.request_json(url) == {"items": [{"name": "Fresh"}]}
    assert len(session.calls) == 1
    assert legacy_path.read_text(encoding="utf-8") == '{"items":[{"name":"Old"}]}'
    assert rift.json_cache_dir == tmp_path / "shared" / "riftcodex" / "json"
    assert rift.image_cache_dir == tmp_path / "shared" / "riftcodex" / "images"
    assert legacy_path.parent == legacy / "json"
    rift.close()


def test_shared_cache_paths_namespace_providers(tmp_path: Path) -> None:
    first_session = _session([])
    second_session = _session([])
    rift = RiftCodexBackend(cache_dir=tmp_path, session=first_session)
    scryfall = ScryfallBackend(cache_dir=tmp_path, session=second_session)
    assert rift.json_cache_dir == tmp_path / "riftcodex" / "json"
    assert rift.image_cache_dir == tmp_path / "riftcodex" / "images"
    assert scryfall.json_cache_dir == tmp_path / "scryfall" / "json"
    assert scryfall.image_cache_dir == tmp_path / "scryfall" / "images"
    assert scryfall.service.bulk_dir == tmp_path / "scryfall" / "bulk"
    assert scryfall.service.metadata_cache_dir == tmp_path / "scryfall" / "metadata"
    rift.close()
    scryfall.close()


def test_backend_explicit_cache_path_precedes_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    environment_root = tmp_path / "environment"
    explicit_root = tmp_path / "explicit"
    monkeypatch.setenv("MTG_SCRIPTS_CACHE_DIR", str(environment_root))
    explicit = RiftCodexBackend(cache_dir=explicit_root, session=_session([]))
    configured = RiftCodexBackend(session=_session([]))
    assert explicit.json_cache_dir == explicit_root / "riftcodex" / "json"
    assert configured.json_cache_dir == environment_root / "riftcodex" / "json"
    assert explicit.legacy_cache_dir is None
    explicit.close()
    configured.close()


def test_legacy_image_is_imported_lazily_without_deleting_source(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    legacy_images = legacy / "images"
    legacy_images.mkdir(parents=True)
    url = "https://example.test/old-card.png"
    image_bytes_path = legacy_images / f"{hashlib.sha256(url.encode()).hexdigest()}.png"
    Image.new("RGB", (8, 4), (80, 20, 10)).save(image_bytes_path)
    old_bytes = image_bytes_path.read_bytes()
    backend = RiftCodexBackend(cache_dir=tmp_path / "shared", session=_session([]))
    backend.legacy_cache_dir = legacy

    image = backend.get_image(url)

    assert image.size == (4, 8)
    assert image_bytes_path.read_bytes() == old_bytes
    assert backend._image_disk_cache.get(canonical_cache_key("GET", url, representation={"kind": "image"})) == old_bytes
    backend.close()


def test_corrupt_legacy_image_is_discarded_and_refetched(tmp_path: Path) -> None:
    legacy_images = tmp_path / "legacy" / "images"
    legacy_images.mkdir(parents=True)
    url = "https://example.test/corrupt-card.png"
    legacy_path = legacy_images / f"{hashlib.sha256(url.encode()).hexdigest()}.png"
    legacy_path.write_bytes(b"corrupt-image")
    output = Path(tmp_path / "expected.png")
    Image.new("RGB", (4, 8), (10, 20, 30)).save(output)
    session = _Session([output.read_bytes()])
    backend = RiftCodexBackend(cache_dir=tmp_path / "new", session=cast("requests.Session", session))
    backend.legacy_cache_dir = tmp_path / "legacy"

    image = backend.get_image(url)

    assert image.size == (4, 8)
    assert len(session.calls) == 1
    assert legacy_path.read_bytes() == b"corrupt-image"
    backend.close()


def test_valid_legacy_current_schema_store_is_copied_and_reused(tmp_path: Path) -> None:
    legacy_root = tmp_path / "old-print-picker-cache"
    legacy_bulk = legacy_root / "bulk"
    old_database = _seed_store(legacy_bulk, [_card()])
    backend = ScryfallBackend(cache_dir=tmp_path / "new-user-cache", session=_session([]))
    backend.service._bulk.legacy_cache_dir = legacy_root
    assert scryfall_store.validate_store(old_database)
    expected_version = backend._cache_name(f"{ORACLE_URI}\n{DEFAULT_URI}")[:16]
    assert old_database == scryfall_store.store_path(legacy_bulk, expected_version)
    backend.service._bulk._migrate_legacy_store()
    assert scryfall_store.validate_store(backend.service.bulk_dir / old_database.name)

    resolved = backend.resolve([backend.parse_line("1 Sol Ring")])[0].card

    assert resolved is not None
    assert resolved.print_id == "fixture-print"
    migrated = backend.service.bulk_dir / old_database.name
    assert migrated.exists()
    assert scryfall_store.validate_store(migrated)
    assert old_database.exists()
    backend.close()


def test_failed_metadata_refresh_uses_last_known_good_and_clear_keeps_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = ScryfallBackend(cache_dir=tmp_path / "cache", session=_session([]))
    bulk_dir = backend.service.bulk_dir
    metadata_path = bulk_dir / "metadata.json"
    path = _seed_store(bulk_dir, [_card()])
    card = backend.resolve([backend.parse_line("1 Sol Ring")])[0].card
    assert card is not None
    active_store = backend.service.store
    assert active_store.path == path

    key = canonical_cache_key("GET", BULK_DATA_URL)
    backend.service.bulk_metadata_cache.put(key, _metadata(), fetched_at=0)
    backend.http.retries = 0

    def fail_request(*_args: object, **_kwargs: object) -> None:
        message = "offline"
        raise requests.ConnectionError(message)

    monkeypatch.setattr(backend.session, "request", fail_request)
    with pytest.warns(RuntimeWarning, match="Using cached Scryfall database"):
        refreshed = backend.refresh_database()
    assert refreshed.path == path
    assert backend.service.store is refreshed
    assert active_store._connection.execute("SELECT COUNT(*) FROM prints").fetchone() == (1,)

    backend.clear_json_cache()
    assert path.exists()
    assert refreshed._connection.execute("SELECT COUNT(*) FROM prints").fetchone() == (1,)
    assert metadata_path.exists()
    backend.close()


def test_invalid_legacy_database_is_not_migrated(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    legacy_bulk = legacy_root / "bulk"
    legacy_bulk.mkdir(parents=True)
    invalid = legacy_bulk / "cards-deadbeef-v6.db"
    invalid.write_bytes(b"not sqlite")
    backend = ScryfallBackend(cache_dir=tmp_path / "new", session=_session([]))
    backend.service._bulk.legacy_cache_dir = legacy_root
    assert not scryfall_store.validate_store(invalid)
    backend.service._bulk._migrate_legacy_store()
    assert not (backend.service.bulk_dir / invalid.name).exists()
    assert invalid.exists()
    backend.close()


def test_corrupt_generation_is_rebuilt_without_overwriting_it(tmp_path: Path) -> None:
    backend = ScryfallBackend(cache_dir=tmp_path / "cache", session=_session([]))
    bulk_dir = backend.service.bulk_dir
    old_path = _seed_store(bulk_dir, [_card()])
    uris = (ORACLE_URI, DEFAULT_URI)
    cards = [_card()]
    for bulk_type, uri, payloads in (
        ("oracle_cards", uris[0], cards),
        ("default_cards", uris[1], cards),
    ):
        bulk_version = backend._cache_name(uri)[:16]
        bulk_path = bulk_dir / f"{bulk_type}-{bulk_version}.jsonl.gz"
        with gzip.open(bulk_path, "wt", encoding="utf-8") as destination:
            for payload in payloads:
                destination.write(json.dumps(payload) + "\n")
    old_path.write_bytes(b"corrupt-current-generation")

    store = backend._card_store()

    assert store.path != old_path
    assert scryfall_store.validate_store(store.path)
    assert old_path.read_bytes() == b"corrupt-current-generation"
    assert not list(bulk_dir.glob("*.jsonl.gz"))
    resolved = backend.resolve([backend.parse_line("1 Sol Ring")])[0].card
    assert resolved is not None
    assert resolved.print_id == "fixture-print"
    backend.close()


def test_two_processes_build_one_scryfall_generation_offline(tmp_path: Path) -> None:
    cache_root = tmp_path / "shared-cache"
    bulk_dir = cache_root / "scryfall" / "bulk"
    bulk_dir.mkdir(parents=True)
    (bulk_dir / "metadata.json").write_text(json.dumps(_metadata()), encoding="utf-8")
    for bulk_type, uri, payload in (
        ("oracle_cards", ORACLE_URI, {"id": "fixture-print"}),
        ("default_cards", DEFAULT_URI, _card()),
    ):
        bulk_version = hashlib.sha256(uri.encode("utf-8")).hexdigest()[:16]
        with gzip.open(bulk_dir / f"{bulk_type}-{bulk_version}.jsonl.gz", "wt", encoding="utf-8") as bulk:
            bulk.write(json.dumps(payload) + "\n")

    script = r"""
import sys
from pathlib import Path
import requests
from mtg_scripts.print_picker.scryfall_backend import ScryfallBackend
def no_network(*args, **kwargs):
    raise AssertionError("unexpected network request")
requests.sessions.Session.request = no_network
backend = ScryfallBackend(cache_dir=Path(sys.argv[1]))
card = backend.resolve([backend.parse_line("1 Sol Ring")])[0].card
assert card is not None and card.print_id == "fixture-print"
backend.close()
"""
    environment = os.environ | {
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    command = [sys.executable, "-B", "-c", script, str(cache_root)]
    first = subprocess.Popen(  # noqa: S603
        command,
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    second = subprocess.Popen(  # noqa: S603
        command,
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    first_output = first.communicate(timeout=30)
    second_output = second.communicate(timeout=30)
    assert first.returncode == second.returncode == 0, first_output[1] + second_output[1]
    generations = list(bulk_dir.glob(f"cards-*-v{scryfall_store.STORE_SCHEMA_VERSION}*.db"))
    assert len(generations) == 1
    assert scryfall_store.validate_store(generations[0])
    assert not list(bulk_dir.glob("*.jsonl.gz"))
