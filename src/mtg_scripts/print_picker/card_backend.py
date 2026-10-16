"""Backend interface and shared HTTP/disk caching for the print picker.

Backends translate a game's API into the immutable `models` types. All caching
that survives a call lives on disk; the only in-memory state is a single map of
in-flight requests used to coalesce duplicate concurrent work.
"""

import hashlib
import io
import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from PIL import Image

from mtg_scripts.common.cache import BytesDiskCache, CachePaths, JsonDiskCache, canonical_cache_key
from mtg_scripts.common.http import JsonHttpClient

if TYPE_CHECKING:
    import requests

    from .models import CardPrint, DeckEntry, Resolution

MAX_EXTENSION_LENGTH: Final[int] = 5
IMAGE_LOADING_ENABLED: Final[bool] = True
JSON_CACHE_MAX_AGE: Final[int] = 24 * 60 * 60

# Arbitrary JSON returned by the card APIs; genuinely dynamic, so it is modeled
# structurally rather than with a TypedDict.
type JSONValue = bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"] | None

type ProgressCallback = Callable[[str, int, int], None]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CardBackend(ABC):
    """Resolves cards and composes shared HTTP/cache services with local image decoding."""

    supports_progress = False
    cache_provider = "print-picker"

    def __init__(self, cache_dir: str | Path | None = None, session: requests.Session | None = None) -> None:
        self.cache_paths = CachePaths.resolve(cache_dir)
        self.json_cache_dir = self.cache_paths.namespace(self.cache_provider, "json")
        self.image_cache_dir = self.cache_paths.namespace(self.cache_provider, "images")
        self.legacy_cache_dir = Path(__file__).with_name(".cache") if cache_dir is None else None
        self._json_disk_cache = JsonDiskCache(self.json_cache_dir, provider=self.cache_provider)
        self._image_disk_cache = BytesDiskCache(self.image_cache_dir)
        self.http = JsonHttpClient(
            session=session,
            user_agent=self.user_agent,
            json_cache=self._json_disk_cache,
            bytes_cache=self._image_disk_cache,
            json_max_age=JSON_CACHE_MAX_AGE,
        )
        self.session = self.http.session

    # -- abstract surface ---------------------------------------------------

    @property
    @abstractmethod
    def user_agent(self) -> str:
        """Return the User-Agent value used for API and image requests."""

    @staticmethod
    @abstractmethod
    def parse_line(line: str) -> DeckEntry:
        """Parse one import line into quantity, name, and an optional print query."""

    @abstractmethod
    def resolve(self, entries: Sequence[DeckEntry], progress: ProgressCallback | None = None) -> list[Resolution]:
        """Resolve import entries to printings, in input order."""

    @abstractmethod
    def printings_of(self, card: CardPrint, progress: ProgressCallback | None = None) -> Sequence[CardPrint]:
        """Return every available printing of the given card."""

    @staticmethod
    @abstractmethod
    def export_card_text(card: CardPrint, entry: DeckEntry) -> str:
        """Return one card in this game's import syntax, without the quantity.

        The result must parse back to the same card via `parse_line`, so that an
        exported list can be re-imported unchanged. Only resolved cards are
        exported, so there is no unresolved case to represent.
        """

    def close(self) -> None:
        """Release every resource held by the backend."""
        self.http.close()

    # -- disk-cached requests ----------------------------------------------

    @staticmethod
    def _cache_name(url: str) -> str:
        """Return the stable digest used by bulk-generation filenames and legacy caches."""
        return _sha256(url)

    def request_json(self, url: str) -> JSONValue:
        key = canonical_cache_key("GET", url)
        if self.legacy_cache_dir is not None:
            self._import_legacy_json(key, url)
        return cast("JSONValue", self.http.get_json(url, max_age=JSON_CACHE_MAX_AGE))

    def request_json_post(self, url: str, payload: Mapping[str, str | int | float | bool | None]) -> JSONValue:
        payload_key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        legacy_key = f"POST {url}\n{payload_key}"
        key = canonical_cache_key("POST", url, payload=payload)
        if self.legacy_cache_dir is not None:
            legacy_name = _sha256(legacy_key)
            self._json_disk_cache.import_legacy(
                key,
                self.legacy_cache_dir / "json" / f"{legacy_name}.json",
                fresh_for_seconds=JSON_CACHE_MAX_AGE,
            )
        return cast("JSONValue", self.http.post_json(url, payload=payload))

    def _import_legacy_json(self, key: str, request_key: str) -> None:
        if self.legacy_cache_dir is None:
            return
        legacy_name = _sha256(request_key)
        self._json_disk_cache.import_legacy(
            key,
            self.legacy_cache_dir / "json" / f"{legacy_name}.json",
            fresh_for_seconds=JSON_CACHE_MAX_AGE,
        )

    def get_image(self, url: str) -> Image.Image:
        key = canonical_cache_key("GET", url, representation={"kind": "image"})
        legacy_path = (
            None
            if self.legacy_cache_dir is None
            else self.legacy_cache_dir / "images" / f"{_sha256(url)}{self._image_extension(url)}"
        )
        if legacy_path is not None and self._image_disk_cache.get(key) is None and legacy_path.is_file():
            with suppress(OSError):
                self._image_disk_cache.put_if_absent(key, legacy_path.read_bytes(), fetched_at=0)
        image: Image.Image | None = None
        for attempt in range(2):
            image_bytes = self.http.get_bytes(url, representation={"kind": "image"}, rate_limiter=None)
            try:
                image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            except OSError, ValueError:
                self._image_disk_cache.discard(key)
                if attempt == 1:
                    raise
                continue
            break
        if image is None:
            message = "Unable to load card image."
            raise RuntimeError(message)
        if image.width > image.height:
            image = image.rotate(90, expand=True)
        return image

    @staticmethod
    def _image_extension(url: str) -> str:
        extension = Path(url.split("?", 1)[0]).suffix.lower() or ".img"
        if len(extension) > MAX_EXTENSION_LENGTH or not extension[1:].isalnum():
            return ".img"
        return extension

    def load_images(self, card: CardPrint, *, high_quality: bool = False) -> tuple[Image.Image, ...]:
        """Return the loaded face images for a printing, front face first."""
        if not IMAGE_LOADING_ENABLED:
            return ()
        return tuple(self.get_image(url) for url in card.image_urls(high_quality=high_quality))

    def load_thumbnails(self, card: CardPrint, size: tuple[int, int]) -> tuple[Image.Image, ...]:
        """Return face images downscaled to fit `size`, for the grid.

        `get_image` decodes a fresh image per call, so these are resized in
        place rather than copied. Full-resolution art is loaded separately, on
        demand, by the image viewer.
        """
        thumbnails = list(self.load_images(card))
        for thumbnail in thumbnails:
            thumbnail.thumbnail(size, Image.Resampling.LANCZOS)
        return tuple(thumbnails)

    # -- cache maintenance --------------------------------------------------

    def clear_json_cache(self) -> None:
        self._json_disk_cache.clear()

    def clear_image_cache(self) -> None:
        self._image_disk_cache.clear()
