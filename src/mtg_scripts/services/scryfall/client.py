"""Scryfall API search with safe pagination and complete-result caching."""

from __future__ import annotations

import warnings
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from mtg_scripts.common.cache import CacheRecord, JsonDiskCache, canonical_cache_key
from mtg_scripts.common.http import HttpRequestError, JsonHttpClient

from .models import ScryfallSearchResult
from .store import card_from_payload

CARDS_SEARCH_URL = "https://api.scryfall.com/cards/search"
SEARCH_CACHE_MAX_AGE = 24 * 60 * 60
NEGATIVE_CACHE_MAX_AGE = 60 * 60
SEARCH_REPRESENTATION_VERSION = 1
HTTP_NOT_FOUND = 404

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


class ScryfallOfflineCacheMissError(RuntimeError):
    """An exact Scryfall query is not present in the offline search cache."""


def validated_next_page(value: object) -> str:
    if not isinstance(value, str):
        message = "Scryfall search response omitted a valid next_page URL."
        raise TypeError(message)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        message = "Scryfall next_page URL is malformed."
        raise ValueError(message) from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.scryfall.com"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        message = "Scryfall next_page URL is outside the trusted API origin."
        raise ValueError(message)
    return value


class ScryfallSearchClient:
    def __init__(
        self,
        http: JsonHttpClient,
        cache: JsonDiskCache,
        *,
        clock: Callable[[], float],
        offline: bool = False,
        allow_stale_data: bool = False,
    ) -> None:
        self.http = http
        self.cache = cache
        self.clock = clock
        self.offline = offline
        self.allow_stale_data = allow_stale_data

    def search(  # noqa: C901, PLR0913
        self,
        query: str,
        *,
        order: str | None = None,
        direction: str | None = None,
        unique: str | None = None,
        max_age: float = SEARCH_CACHE_MAX_AGE,
        allow_stale_data: bool | None = None,
        offline: bool | None = None,
        price_sensitive: bool = False,
    ) -> ScryfallSearchResult:
        params: dict[str, str] = {"q": query}
        if order is not None:
            params["order"] = order
        if direction is not None:
            params["dir"] = direction
        if unique is not None:
            params["unique"] = unique
        key = canonical_cache_key(
            "GET",
            CARDS_SEARCH_URL,
            params=params,
            representation={"scryfall_search": SEARCH_REPRESENTATION_VERSION},
        )
        allow_stale = self.allow_stale_data if allow_stale_data is None else allow_stale_data
        offline_mode = self.offline if offline is None else offline
        cached = self.cache.get(key, max_age=max_age)
        if cached is not None and self._negative_is_fresh(cached, max_age):
            return self._snapshot(cached, stale=False)
        stale = cached if cached is not None else self.cache.get(key, allow_stale=True)
        if offline_mode:
            if stale is not None and allow_stale:
                return self._stale_snapshot(stale, query, price_sensitive=price_sensitive)
            message = f"No fresh cached Scryfall search result for query: {query}"
            raise ScryfallOfflineCacheMissError(message)

        def fetch_result() -> dict[str, object]:
            try:
                records, not_found = self._fetch_complete(params)
            except HttpRequestError as error:
                if error.status_code != HTTP_NOT_FOUND:
                    raise
                records, not_found = [], True
            return {"cards": records, "not_found": not_found}

        def result_ttl(value: object) -> float:
            return NEGATIVE_CACHE_MAX_AGE if isinstance(value, dict) and value.get("cards") == [] else max_age

        try:
            record = self.cache.get_or_fetch(
                key,
                fetch_result,
                max_age=max_age,
                freshness=result_ttl,
            )
        except HttpRequestError:
            if stale is not None and allow_stale:
                return self._stale_snapshot(stale, query, price_sensitive=price_sensitive)
            raise
        return self._snapshot(record, stale=False)

    def _negative_is_fresh(self, record: CacheRecord[object], max_age: float) -> bool:
        value = record.value
        if not isinstance(value, dict):
            return False
        cards = value.get("cards")
        if not isinstance(cards, list):
            return False
        if cards:
            return True
        return self.clock() - record.fetched_at <= min(max_age, NEGATIVE_CACHE_MAX_AGE)

    def _snapshot(self, record: CacheRecord[object], *, stale: bool) -> ScryfallSearchResult:
        value = record.value
        if not isinstance(value, dict) or not isinstance(value.get("cards"), list):
            message = "Cached Scryfall search result has an invalid shape."
            raise TypeError(message)
        cards = value["cards"]
        if any(not isinstance(card, dict) for card in cards):
            message = "Cached Scryfall search contains a malformed card record."
            raise TypeError(message)
        return ScryfallSearchResult(tuple(card_from_payload(card) for card in cards), record.fetched_at, stale)

    def _stale_snapshot(
        self, record: CacheRecord[object], query: str, *, price_sensitive: bool
    ) -> ScryfallSearchResult:
        result = self._snapshot(record, stale=True)
        fetched_at = datetime.fromtimestamp(result.fetched_at).astimezone().isoformat()
        subject = "prices" if price_sensitive else "card data"
        warnings.warn(
            f"Using stale Scryfall {subject} from {fetched_at} for query {query!r}.",
            RuntimeWarning,
            stacklevel=2,
        )
        return result

    def _fetch_complete(self, params: Mapping[str, str]) -> tuple[list[dict[str, object]], bool]:
        cards: list[dict[str, object]] = []
        payload = self.http.get_json(CARDS_SEARCH_URL, params=params, use_cache=False)
        visited: set[str] = set()
        while True:
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                message = "Scryfall search response does not contain a card data list."
                raise TypeError(message)
            for card in payload["data"]:
                if not isinstance(card, dict) or not isinstance(card.get("id"), str):
                    message = "Scryfall search response contains a malformed card."
                    raise TypeError(message)
                cards.append(card)
            if payload.get("has_more") is not True:
                break
            next_page = validated_next_page(payload.get("next_page"))
            if next_page in visited:
                message = "Scryfall pagination repeated a next_page URL."
                raise ValueError(message)
            visited.add(next_page)
            payload = self.http.get_json(next_page, use_cache=False)
        return cards, not cards
