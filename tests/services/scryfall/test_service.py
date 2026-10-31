from __future__ import annotations

import gzip
import io
import json
from typing import TYPE_CHECKING, cast, override

import pytest
import requests

from mtg_scripts.common.cache import CacheError
from mtg_scripts.mana_base_creator import scryfall
from mtg_scripts.other_scripts import vanilla
from mtg_scripts.services.scryfall import store
from mtg_scripts.services.scryfall.client import (
    CARDS_SEARCH_URL,
    ScryfallOfflineCacheMissError,
    validated_next_page,
)
from mtg_scripts.services.scryfall.progress import DownloadSnapshot, ProgressIndicator
from mtg_scripts.services.scryfall.service import ScryfallService

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from requests import Session


class _Response:
    def __init__(
        self,
        payload: object = None,
        *,
        content: bytes = b"",
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.content = content
        self.status_code = status
        self.headers = dict(headers or {})
        self.closed = False

    def json(self) -> object:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            message = f"HTTP {self.status_code}"
            raise requests.HTTPError(message)

    def iter_content(self, *, chunk_size: int) -> list[bytes]:
        assert chunk_size > 0
        return [self.content]

    def close(self) -> None:
        self.closed = True


class _Session:
    def __init__(self, responses: list[_Response | Exception]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.closed = False

    def request(self, method: str, url: str, **kwargs: object) -> _Response:
        self.calls.append((method, url, kwargs))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self) -> None:
        self.closed = True


def _session(responses: Sequence[object]) -> tuple[Session, _Session]:
    supported = [response for response in responses if isinstance(response, (_Response, Exception))]
    if len(supported) != len(responses):
        message = "Test session responses must be fake responses or exceptions."
        raise TypeError(message)
    fake = _Session(supported)
    return cast("Session", fake), fake


def _card(print_id: str, oracle_id: str = "oracle-1", *, name: str = "Fetch Land") -> dict[str, object]:
    return {
        "object": "card",
        "id": print_id,
        "oracle_id": oracle_id,
        "name": name,
        "set": "tst",
        "set_name": "Test Set",
        "set_type": "expansion",
        "games": ["paper"],
        "collector_number": "1",
        "released_at": "2026-01-01",
        "finishes": ["nonfoil"],
        "image_uris": {"normal": f"https://example.test/{print_id}.jpg"},
        "oracle_text": "Search your library for a land card.",
        "legalities": {"commander": "legal"},
        "prices": {"usd": "1.25"},
    }


def _gzip_jsonl(payload: object) -> bytes:
    stream = io.BytesIO()
    with gzip.GzipFile(fileobj=stream, mode="wb") as destination:
        destination.write((json.dumps(payload) + "\n").encode("utf-8"))
    return stream.getvalue()


def _bulk_metadata(*, include_tags: bool) -> dict[str, object]:
    entries: list[dict[str, str]] = [
        {
            "type": "oracle_cards",
            "jsonl_download_uri": "https://data.scryfall.io/oracle.jsonl.gz",
            "updated_at": "2026-10-15",
        },
        {
            "type": "default_cards",
            "jsonl_download_uri": "https://data.scryfall.io/default.jsonl.gz",
            "updated_at": "2026-10-15",
        },
    ]
    if include_tags:
        entries.append(
            {
                "type": "oracle_tags",
                "jsonl_download_uri": "https://data.scryfall.io/tags.jsonl.gz",
                "updated_at": "2026-10-15",
            }
        )
    return {"data": entries}


def test_bulk_service_builds_payload_store_and_optional_oracle_tag_index(tmp_path: Path) -> None:
    tag = {
        "object": "tag",
        "id": "tag-1",
        "type": "oracle",
        "slug": "cycle-fetchland",
        "taggings": [{"oracle_id": "oracle-1", "weight": "median"}],
    }
    responses = [
        _Response(_bulk_metadata(include_tags=True)),
        _Response(content=_gzip_jsonl({"id": "print-1", "oracle_id": "oracle-1"})),
        _Response(content=_gzip_jsonl(_card("print-1"))),
        _Response(content=_gzip_jsonl(tag)),
    ]
    session, fake = _session(responses)
    service = ScryfallService(
        cache_dir=tmp_path, session=session, sleep=lambda _: None, random_uniform=lambda _a, _b: 0
    )

    database = service.store
    matches = database.by_name(["Fetch Land"])["fetch land"]
    tagged = service.cards_for_tag("otag:cycle-fetchland")

    assert database.has_oracle_tags
    assert [match.card.print_id for match in matches] == ["print-1"]
    assert tagged is not None
    assert [card.print_id for card in tagged] == ["print-1"]
    assert tagged[0].prices["usd"] == "1.25"
    assert fake.calls[0][1] == "https://api.scryfall.com/bulk-data"
    assert len(fake.calls) == 4
    service.close()
    assert not fake.closed


def test_older_bulk_metadata_builds_without_tags_and_signals_unavailable(tmp_path: Path) -> None:
    session, fake = _session(
        [
            _Response(_bulk_metadata(include_tags=False)),
            _Response(content=_gzip_jsonl({"id": "print-1", "oracle_id": "oracle-1"})),
            _Response(content=_gzip_jsonl(_card("print-1"))),
        ]
    )
    service = ScryfallService(
        cache_dir=tmp_path, session=session, sleep=lambda _: None, random_uniform=lambda _a, _b: 0
    )
    assert not service.store.has_oracle_tags
    assert service.cards_for_tag("cycle-fetchland") is None
    assert len(fake.calls) == 3
    service.close()


def test_arbitrary_search_paginates_once_and_caches_only_complete_result(tmp_path: Path) -> None:
    next_page = "https://api.scryfall.com/cards/search?q=test&page=2"
    page_one = {"data": [_card("first")], "has_more": True, "next_page": next_page}
    page_two = {"data": [_card("second", name="Other Land")], "has_more": False}
    session, fake = _session([_Response(page_one), _Response(page_two)])
    service = ScryfallService(
        cache_dir=tmp_path, session=session, sleep=lambda _: None, random_uniform=lambda _a, _b: 0
    )

    first = service.search('name:"Fetch Land"', order="price", direction="asc", unique="cards")
    second = service.search('name:"Fetch Land"', order="price", direction="asc", unique="cards")

    assert [card.print_id for card in first.cards] == ["first", "second"]
    assert second.fetched_at == pytest.approx(first.fetched_at, abs=1e-6)
    assert not first.stale
    assert not second.stale
    assert len(fake.calls) == 2
    assert fake.calls[0][1] == CARDS_SEARCH_URL
    assert fake.calls[0][2]["params"] == {"q": 'name:"Fetch Land"', "order": "price", "dir": "asc", "unique": "cards"}
    assert fake.calls[1][1] == next_page
    assert not list(service.bulk_dir.glob("cards-*.db"))
    service.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://api.scryfall.com/cards/search?page=2",
        "https://evil.example/cards/search?page=2",
        "https://user@api.scryfall.com/cards/search?page=2",
        "https://api.scryfall.com:444/cards/search?page=2",
    ],
)
def test_next_page_must_stay_on_https_scryfall_api_origin(url: str) -> None:
    with pytest.raises(ValueError, match="trusted API origin"):
        validated_next_page(url)


def test_malformed_or_repeated_next_page_is_not_cached(tmp_path: Path) -> None:
    next_page = "https://api.scryfall.com/cards/search?page=2"
    session, fake = _session(
        [
            _Response({"data": [_card("first")], "has_more": True, "next_page": "https://evil.example/"}),
            _Response({"data": [_card("first")], "has_more": True, "next_page": next_page}),
            _Response({"data": [_card("second")], "has_more": True, "next_page": next_page}),
        ]
    )
    service = ScryfallService(
        cache_dir=tmp_path, session=session, sleep=lambda _: None, random_uniform=lambda _a, _b: 0
    )
    with pytest.raises(ValueError, match="trusted API origin"):
        service.search("tag:test")
    with pytest.raises(ValueError, match="repeated"):
        service.search("tag:test")
    assert len(fake.calls) == 3
    service.close()


def test_404_no_results_are_cached_for_one_hour_only(tmp_path: Path) -> None:
    now = [100.0]
    session, fake = _session(
        [
            _Response({"details": "No cards found"}, status=404),
            _Response({"data": [_card("found")], "has_more": False}),
        ]
    )
    service = ScryfallService(
        cache_dir=tmp_path, session=session, clock=lambda: now[0], sleep=lambda _: None, random_uniform=lambda _a, _b: 0
    )
    assert service.search("tag:maybe").cards == ()
    now[0] += 59 * 60
    assert service.search("tag:maybe").cards == ()
    assert len(fake.calls) == 1
    now[0] += 61
    assert [card.print_id for card in service.search("tag:maybe").cards] == ["found"]
    assert len(fake.calls) == 2
    service.close()


def test_offline_search_requires_exact_cache_and_explicit_stale_permission(tmp_path: Path) -> None:
    now = [100.0]
    session, _fake = _session([_Response({"data": [_card("cached")], "has_more": False})])
    service = ScryfallService(
        cache_dir=tmp_path, session=session, clock=lambda: now[0], sleep=lambda _: None, random_uniform=lambda _a, _b: 0
    )
    assert service.search("name:cached", max_age=1).cards[0].print_id == "cached"
    now[0] += 10
    with pytest.raises(ScryfallOfflineCacheMissError):
        service.search("name:cached", max_age=1, offline=True)
    with pytest.warns(RuntimeWarning, match="stale Scryfall prices"):
        stale = service.search("name:cached", max_age=1, offline=True, allow_stale_data=True, price_sensitive=True)
    assert stale.stale
    assert stale.cards[0].print_id == "cached"
    with pytest.raises(ScryfallOfflineCacheMissError):
        service.search("name:never-cached", offline=True, allow_stale_data=True)
    service.close()


def test_offline_mode_never_fetches_bulk_and_requires_compatible_store(tmp_path: Path) -> None:
    session, fake = _session([])
    service = ScryfallService(cache_dir=tmp_path, session=session, offline=True)
    with pytest.raises(CacheError, match="Offline Scryfall mode has no compatible local card database"):
        _ = service.store
    assert fake.calls == []
    service.close()


def test_offline_mode_uses_an_existing_compatible_store(tmp_path: Path) -> None:
    bulk_dir = tmp_path / "scryfall" / "bulk"
    path = store.store_path(bulk_dir, "local-version")
    store.build_from_cards(path, [_card("cached")])
    session, fake = _session([])
    service = ScryfallService(cache_dir=tmp_path, session=session, offline=True)
    with pytest.warns(RuntimeWarning, match="offline mode"):
        database = service.store
    assert database.path == path
    assert service.resolve_names(["Fetch Land"])["fetch land"][0].card.print_id == "cached"
    assert fake.calls == []
    service.close()


def test_tag_service_reports_incomplete_local_printing_coverage(tmp_path: Path) -> None:
    bulk_dir = tmp_path / "scryfall" / "bulk"
    path = store.store_path(bulk_dir, "incomplete-tags")
    tags = [
        {
            "object": "tag",
            "type": "oracle",
            "slug": "fetchland",
            "taggings": [
                {"oracle_id": "oracle-1"},
                {"oracle_id": "oracle-without-print"},
            ],
        }
    ]
    store.build_from_cards(path, [_card("local")], tags=tags)
    session, fake = _session([])
    service = ScryfallService(cache_dir=tmp_path, session=session, offline=True)

    with pytest.warns(RuntimeWarning, match="offline mode"):
        assert service.cards_for_tag("fetchland") is None
    assert fake.calls == []
    service.close()


def test_mana_base_and_vanilla_reuse_the_shared_search_cache(tmp_path: Path) -> None:
    query = "game:paper legal:commander order:usd dir:asc otag:cycle-fetchland"
    vanilla_query = "type:creature commander:wg (game:paper) is:vanilla"
    payload = _card("shared-print", name="Vanilla Fetch Land")
    payload.update(
        {
            "type_line": "Creature - Giant",
            "mana_value": 2,
            "cmc": 2,
            "mana_cost": "{1}{G}",
            "power": "4",
            "toughness": "4",
        }
    )
    first_session, first_fake = _session([_Response({"data": [payload], "has_more": False}) for _ in range(2)])
    service = ScryfallService(
        cache_dir=tmp_path,
        session=first_session,
        prefer_local_search=False,
        clock=lambda: 1000,
        sleep=lambda _: None,
        random_uniform=lambda _a, _b: 0,
    )

    assert scryfall.query_scryfall(query, service)[0].name == "Vanilla Fetch Land"
    assert vanilla.fetch_scryfall_cards(vanilla_query, service)[0].name == "Vanilla Fetch Land"
    service.close()
    assert len(first_fake.calls) == 2

    second_session, second_fake = _session([])
    cached_service = ScryfallService(
        cache_dir=tmp_path,
        session=second_session,
        prefer_local_search=False,
        clock=lambda: 1001,
        sleep=lambda _: None,
        random_uniform=lambda _a, _b: 0,
    )
    assert scryfall.query_scryfall(query, cached_service)[0].name == "Vanilla Fetch Land"
    assert vanilla.fetch_scryfall_cards(vanilla_query, cached_service)[0].name == "Vanilla Fetch Land"
    assert second_fake.calls == []
    cached_service.close()


def _printing(print_id: str, oracle_id: str, name: str, **overrides: object) -> dict[str, object]:
    payload = _card(print_id, oracle_id, name=name)
    payload.update(overrides)
    return payload


def _offline_service(
    tmp_path: Path, cards: list[dict[str, object]], tags: list[dict[str, object]] | None = None
) -> tuple[ScryfallService, _Session]:
    store.build_from_cards(store.store_path(tmp_path / "scryfall" / "bulk", "local"), cards, tags=tags)
    session, fake = _session([])
    return ScryfallService(cache_dir=tmp_path, session=session, offline=True), fake


@pytest.mark.filterwarnings("ignore:Using cached Scryfall database")
def test_local_search_picks_cheapest_paper_printing_per_tagged_card_without_api(tmp_path: Path) -> None:
    cards = [
        _printing("fetch-expensive", "fetch-1", "Fabled Passage", prices={"eur": "8.00"}),
        _printing("fetch-cheap", "fetch-1", "Fabled Passage", prices={"eur": "3.00"}),
        _printing("fetch-unpriced", "fetch-1", "Fabled Passage", prices={"eur": None}),
        _printing("digital", "fetch-2", "Digital Fetch", games=["arena"], prices={"eur": "0.01"}),
        _printing("banned", "fetch-3", "Banned Fetch", legalities={"commander": "banned"}, prices={"eur": "0.02"}),
        _printing("pricey", "fetch-4", "Pricey Fetch", prices={"eur": "20.00"}),
    ]
    tags: list[dict[str, object]] = [
        {
            "object": "tag",
            "type": "oracle",
            "slug": "cycle-fetchland",
            "taggings": [{"oracle_id": oracle_id} for oracle_id in ("fetch-1", "fetch-2", "fetch-3", "fetch-4")],
        }
    ]
    service, fake = _offline_service(tmp_path, cards, tags)

    result = scryfall.query_scryfall("game:paper legal:commander order:eur dir:asc otag:cycle-fetchland", service)

    assert [card.print_id for card in result] == ["fetch-cheap", "pricey"]
    assert fake.calls == []
    service.close()


@pytest.mark.filterwarnings("ignore:Using cached Scryfall database")
def test_local_search_supports_mdfc_produces_and_face_oracle_text(tmp_path: Path) -> None:
    def mdfc(print_id: str, name: str, produced: list[str], text: str) -> dict[str, object]:
        return _printing(
            print_id,
            f"oracle-{print_id}",
            name,
            layout="modal_dfc",
            type_line="Sorcery // Land",
            oracle_text=None,
            produced_mana=produced,
            card_faces=[{"name": "Front", "oracle_text": "Deal 3 damage."}, {"name": "Back", "oracle_text": text}],
        )

    untapped = "As this land enters, you may pay 3 life. If you don't, it enters tapped.\n{T}: Add {R}."
    cards = [
        mdfc("one-color", "Shatterskull Smashing", ["R"], untapped),
        mdfc("two-color", "Dual Mdfc", ["R", "G"], untapped),
        _printing("plain", "oracle-plain", "Plain Land", type_line="Land", oracle_text=untapped, produced_mana=["R"]),
    ]
    service, fake = _offline_service(tmp_path, cards)

    result = service.search('is:mdfc t:land -produces:m o:"may pay 3 life"')

    assert [card.name for card in result.cards] == ["Shatterskull Smashing"]
    assert "may pay 3 life" in result.cards[0].oracle_text
    assert fake.calls == []
    service.close()


@pytest.mark.filterwarnings("ignore:Using cached Scryfall database")
def test_local_search_exact_name_identity_and_extras(tmp_path: Path) -> None:
    cards = [
        _printing("tower-new", "tower", "Command Tower", prices={"usd": "3.00"}),
        _printing("tower-old", "tower", "Command Tower", prices={"usd": "0.50"}),
        _printing(
            "bear", "bear", "Grizzly Bears", type_line="Creature - Bear", oracle_text="", color_identity=["G"], cmc=2
        ),
        _printing(
            "token", "bear-token", "Bear", type_line="Token Creature - Bear", oracle_text="", layout="token", cmc=0
        ),
        _printing("ogre", "ogre", "Gray Ogre", type_line="Creature - Ogre", oracle_text="", color_identity=["R"]),
    ]
    service, fake = _offline_service(tmp_path, cards)

    tower = service.search('game:paper legal:commander order:usd dir:asc !"Command Tower"')
    vanilla_cards = service.search("type:creature commander:wg (game:paper) is:vanilla", order="cmc", direction="asc")

    assert [card.print_id for card in tower.cards] == ["tower-old"]
    assert [card.name for card in vanilla_cards.cards] == ["Grizzly Bears"]
    assert fake.calls == []
    service.close()


def test_unsupported_syntax_uses_the_api_without_building_the_local_database(tmp_path: Path) -> None:
    session, fake = _session([_Response({"data": [_card("api")], "has_more": False})])
    service = ScryfallService(
        cache_dir=tmp_path, session=session, sleep=lambda _: None, random_uniform=lambda _a, _b: 0
    )

    assert [card.print_id for card in service.search("t:land or t:creature").cards] == ["api"]
    assert [call[1] for call in fake.calls] == [CARDS_SEARCH_URL]
    assert not list(service.bulk_dir.glob("cards-*.db"))
    service.close()


def test_rate_limited_search_waits_out_the_lockout_and_reports_it(tmp_path: Path) -> None:
    sleeps: list[float] = []
    session, _fake = _session([_Response({}, status=429), _Response({"data": [_card("api")], "has_more": False})])
    progress = _RecordingProgress()
    service = ScryfallService(
        cache_dir=tmp_path,
        session=session,
        progress=progress,
        clock=lambda: 0,
        sleep=sleeps.append,
        random_uniform=lambda _a, _b: 0,
    )

    assert service.search("name:api").cards[0].print_id == "api"
    assert 30.0 in sleeps
    assert any("HTTP 429" in message for message in progress.statuses)
    service.close()


def test_bulk_download_reports_named_progress(tmp_path: Path) -> None:
    responses = [
        _Response(_bulk_metadata(include_tags=False)),
        _Response(content=_gzip_jsonl({"id": "print-1", "oracle_id": "oracle-1"})),
        _Response(content=_gzip_jsonl(_card("print-1"))),
    ]
    session, _fake = _session(responses)
    progress = _RecordingProgress()
    service = ScryfallService(
        cache_dir=tmp_path, session=session, progress=progress, sleep=lambda _: None, random_uniform=lambda _a, _b: 0
    )

    _ = service.store

    finished = [snapshot for snapshot in progress.downloads if snapshot.finished]
    assert [snapshot.source for snapshot in finished] == ["oracle.jsonl.gz", "default.jsonl.gz"]
    assert all(snapshot.current > 0 for snapshot in finished)
    assert any("Building" in message for message in progress.statuses)
    assert progress.idle_calls >= 1
    service.close()


class _RecordingProgress(ProgressIndicator):
    def __init__(self) -> None:
        super().__init__(render_interval=0)
        self.downloads: list[DownloadSnapshot] = []
        self.statuses: list[str] = []
        self.idle_calls = 0

    @override
    def render_download(self, snapshot: DownloadSnapshot) -> None:
        self.downloads.append(snapshot)

    @override
    def render_status(self, message: str) -> None:
        self.statuses.append(message)

    @override
    def render_idle(self) -> None:
        self.idle_calls += 1
