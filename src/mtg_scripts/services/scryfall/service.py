"""Scryfall bulk-backed records, oracle-tag lookup, and cached API search."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import TYPE_CHECKING, Self

from mtg_scripts.common.cache import CachePaths, JsonDiskCache
from mtg_scripts.common.http import DiskRateLimiter, JsonHttpClient

from .bulk import ScryfallBulkData
from .client import SEARCH_CACHE_MAX_AGE, ScryfallSearchClient

SCRYFALL_USER_AGENT = "mtg-scripts/1.0 (contact: local)"

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import requests

    from .models import ProgressCallback, ScryfallCard, ScryfallNameMatch, ScryfallSearchResult
    from .store import CardStore


class ScryfallService:
    """Own or borrow shared Scryfall HTTP, database, tag, and search resources."""

    def __init__(  # noqa: PLR0913
        self,
        cache_dir: str | Path | None = None,
        *,
        session: requests.Session | None = None,
        http_client: JsonHttpClient | None = None,
        offline: bool = False,
        allow_stale_data: bool = False,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.paths = CachePaths.resolve(cache_dir)
        self._owns_http = http_client is None
        self.http = http_client or JsonHttpClient(
            session=session,
            user_agent=SCRYFALL_USER_AGENT,
            clock=clock,
            sleep=sleep,
            random_uniform=random_uniform,
            rate_limiter=DiskRateLimiter(
                self.paths.namespace("scryfall", "metadata") / ".api-rate.lock",
                min_interval=0.1,
                clock=clock,
                sleep=sleep,
            ),
        )
        if self.http.rate_limiter is None:
            self.http.rate_limiter = DiskRateLimiter(
                self.paths.namespace("scryfall", "metadata") / ".api-rate.lock",
                min_interval=0.1,
                clock=clock,
                sleep=sleep,
            )
        self._bulk = ScryfallBulkData(
            self.paths,
            self.http,
            legacy_cache_dir=Path(__file__).parents[2] / "print_picker" / ".cache" if cache_dir is None else None,
            offline=offline,
            clock=clock,
        )
        self.search_cache = JsonDiskCache(self.paths.namespace("scryfall", "search"), provider="scryfall", clock=clock)
        self.search_client = ScryfallSearchClient(
            self.http,
            self.search_cache,
            clock=clock,
            offline=offline,
            allow_stale_data=allow_stale_data,
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

    def get_store(self, progress: ProgressCallback | None = None, *, force_refresh: bool = False) -> CardStore:
        return self._bulk.get_store(progress, force_refresh=force_refresh)

    @property
    def metadata_cache_dir(self) -> Path:
        return self._bulk.metadata_cache_dir

    @property
    def has_oracle_tags(self) -> bool:
        return bool(self.store.has_oracle_tags)

    def resolve_names(
        self,
        names: Sequence[str],
        *,
        include_flavor: bool = True,
        progress: ProgressCallback | None = None,
    ) -> dict[str, list[ScryfallNameMatch]]:
        if not names:
            return {}
        return self._bulk.get_store(progress).by_name(names, include_flavor=include_flavor)

    def by_print_id(self, print_id: str, *, progress: ProgressCallback | None = None) -> ScryfallCard | None:
        return self._bulk.get_store(progress).by_print_id(print_id)

    def printings_of(self, oracle_id: str, *, progress: ProgressCallback | None = None) -> list[ScryfallCard]:
        return self._bulk.get_store(progress).printings_of(oracle_id)

    def cards_for_tag(self, slug: str, *, progress: ProgressCallback | None = None) -> list[ScryfallCard] | None:
        """Return local tag printings, or `None` when tags/printing coverage is incomplete."""
        store = self._bulk.get_store(progress)
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
    ) -> ScryfallSearchResult:
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

    def refresh_bulk(self, progress: ProgressCallback | None = None) -> CardStore:
        return self._bulk.refresh(progress)

    def clear_search_cache(self) -> None:
        self.search_cache.clear()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._bulk.close()
        if self._owns_http:
            self.http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
