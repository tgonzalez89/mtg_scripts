"""Scryfall bulk-backed records, oracle-tag lookup, and local-first card search."""

from __future__ import annotations

import random
import sqlite3
import time
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Self

from mtg_scripts.common.cache import CacheError, CachePaths, JsonDiskCache
from mtg_scripts.common.http import HTTP_TOO_MANY_REQUESTS, DiskRateLimiter, HttpRequestError, JsonHttpClient

from .bulk import ScryfallBulkData
from .client import SEARCH_CACHE_MAX_AGE, SEARCH_MIN_INTERVAL, ScryfallSearchClient
from .models import ScryfallSearchResult
from .progress import ProgressIndicator, SilentProgressIndicator
from .query import parse_local_query, select_results

SCRYFALL_USER_AGENT = "mtg-scripts/1.0 (contact: local)"
API_MIN_INTERVAL = 0.1
# Scryfall locks a client out for 30 seconds after an HTTP 429.
RATE_LIMITED_DELAY = 30.0

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import requests

    from .models import ScryfallCard, ScryfallNameMatch
    from .store import CardStore


class ScryfallService:
    """Own or borrow shared Scryfall HTTP, database, tag, and search resources.

    `progress` decides how downloads, database builds, and API waits are shown, e.g.
    `TerminalProgressIndicator` for scripts or `progress_tk.TkProgressIndicator` for Tk apps.
    Searches are answered from the local bulk database whenever the query syntax allows it.
    """

    def __init__(  # noqa: PLR0913
        self,
        cache_dir: str | Path | None = None,
        *,
        session: requests.Session | None = None,
        http_client: JsonHttpClient | None = None,
        offline: bool = False,
        allow_stale_data: bool = False,
        prefer_local_search: bool = True,
        progress: ProgressIndicator | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.paths = CachePaths.resolve(cache_dir)
        self.progress = progress if progress is not None else SilentProgressIndicator()
        self.prefer_local_search = prefer_local_search
        metadata_dir = self.paths.namespace("scryfall", "metadata")
        self._owns_http = http_client is None
        self.http = http_client or JsonHttpClient(
            session=session,
            user_agent=SCRYFALL_USER_AGENT,
            clock=clock,
            sleep=sleep,
            random_uniform=random_uniform,
        )
        if self.http.rate_limiter is None:
            self.http.rate_limiter = DiskRateLimiter(
                metadata_dir / ".api-rate.lock", min_interval=API_MIN_INTERVAL, clock=clock, sleep=sleep
            )
        if self.http.rate_limited_delay is None:
            self.http.rate_limited_delay = RATE_LIMITED_DELAY
        if self.http.on_retry is None:
            self.http.on_retry = self._report_retry
        self._bulk = ScryfallBulkData(
            self.paths,
            self.http,
            legacy_cache_dir=Path(__file__).parents[2] / "print_picker" / ".cache" if cache_dir is None else None,
            offline=offline,
            clock=clock,
            progress=self.progress,
        )
        self.search_cache = JsonDiskCache(self.paths.namespace("scryfall", "search"), provider="scryfall", clock=clock)
        self.search_client = ScryfallSearchClient(
            self.http,
            self.search_cache,
            clock=clock,
            offline=offline,
            allow_stale_data=allow_stale_data,
            rate_limiter=DiskRateLimiter(
                metadata_dir / ".search-rate.lock", min_interval=SEARCH_MIN_INTERVAL, clock=clock, sleep=sleep
            ),
            progress=self.progress,
        )
        self._closed = False

    @property
    def bulk_dir(self) -> Path:
        return self._bulk.bulk_dir

    @property
    def bulk_metadata_cache(self) -> JsonDiskCache:
        return self._bulk.metadata_cache

    @property
    def store(self) -> CardStore:
        return self._bulk.get_store()

    def get_store(self, *, force_refresh: bool = False) -> CardStore:
        return self._bulk.get_store(force_refresh=force_refresh)

    @property
    def metadata_cache_dir(self) -> Path:
        return self._bulk.metadata_cache_dir

    @property
    def has_oracle_tags(self) -> bool:
        return bool(self.store.has_oracle_tags)

    def resolve_names(self, names: Sequence[str], *, include_flavor: bool = True) -> dict[str, list[ScryfallNameMatch]]:
        if not names:
            return {}
        return self._bulk.get_store().by_name(names, include_flavor=include_flavor)

    def by_print_id(self, print_id: str) -> ScryfallCard | None:
        return self._bulk.get_store().by_print_id(print_id)

    def printings_of(self, oracle_id: str) -> list[ScryfallCard]:
        return self._bulk.get_store().printings_of(oracle_id)

    def cards_for_tag(self, slug: str) -> list[ScryfallCard] | None:
        """Return local tag printings, or `None` when tags/printing coverage is incomplete."""
        store = self._bulk.get_store()
        if not store.has_complete_tag_printings(slug):
            return None
        return store.cards_for_tag(slug)

    def search(  # noqa: PLR0913
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
        prefer_local: bool | None = None,
    ) -> ScryfallSearchResult:
        """Search with Scryfall syntax: locally when every term is supported, otherwise through the API."""
        if self.prefer_local_search if prefer_local is None else prefer_local:
            local = self.search_local(query, order=order, direction=direction, unique=unique)
            if local is not None:
                return local
        return self.search_client.search(
            query,
            order=order,
            direction=direction,
            unique=unique,
            max_age=max_age,
            allow_stale_data=allow_stale_data,
            offline=offline,
            price_sensitive=price_sensitive,
        )

    def search_local(
        self,
        query: str,
        *,
        order: str | None = None,
        direction: str | None = None,
        unique: str | None = None,
    ) -> ScryfallSearchResult | None:
        """Answer a query from the bulk database, or return `None` if it needs the API.

        Supported: `game:`, `legal:commander`, `t:`, `o:`, `otag:`, `is:mdfc|split|flip|transform|vanilla`,
        `produces:<color>|m`, `id:`/`commander:` (color letters), `!"exact name"`, `-` negation,
        and `order:usd|eur|tix|cmc|name|released`, `dir:`, `unique:cards|prints`.
        """
        parsed = parse_local_query(query, order=order, direction=direction, unique=unique)
        if parsed is None:
            return None
        try:
            store = self._bulk.get_store()
        except (CacheError, HttpRequestError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            warnings.warn(
                f"Local Scryfall database unavailable ({error}); falling back to the API.",
                RuntimeWarning,
                stacklevel=2,
            )
            return None
        cards = store.search(parsed)
        if cards is None:
            return None
        return ScryfallSearchResult(tuple(select_results(cards, parsed)), store.path.stat().st_mtime)

    def refresh_bulk(self) -> CardStore:
        return self._bulk.refresh()

    def clear_search_cache(self) -> None:
        self.search_cache.clear()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._bulk.close()
        if self._owns_http:
            self.http.close()

    def _report_retry(self, url: str, status_code: int | None, delay: float) -> None:
        if status_code == HTTP_TOO_MANY_REQUESTS:
            reason = "Scryfall rate limit reached (HTTP 429)"
        elif status_code is not None:
            reason = f"Scryfall returned HTTP {status_code}"
        else:
            reason = "Connection to Scryfall failed"
        self.progress.status(f"{reason} for {url}; retrying in {delay:.0f}s...")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
