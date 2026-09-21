"""Backend interface and shared HTTP/disk caching for the print picker.

Backends translate a game's API into the immutable `models` types. All caching
that survives a call lives on disk; the only in-memory state is a single map of
in-flight requests used to coalesce duplicate concurrent work.
"""

import hashlib
import io
import json
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import requests
from PIL import Image

if TYPE_CHECKING:
    from .models import CardPrint, DeckEntry, Resolution

MAX_EXTENSION_LENGTH: Final[int] = 5
IMAGE_LOADING_ENABLED: Final[bool] = True

# Arbitrary JSON returned by the card APIs; genuinely dynamic, so it is modeled
# structurally rather than with a TypedDict.
type JSONValue = bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"] | None

type ProgressCallback = Callable[[str, int, int], None]


class CardBackend(ABC):
    """Resolves import lines into immutable `CardPrint`s and loads their images."""

    supports_progress = False

    def __init__(self, cache_dir: str | Path | None = None, session: requests.Session | None = None) -> None:
        root = Path(cache_dir or Path(__file__).with_name(".cache"))
        self.json_cache_dir = root / "json"
        self.image_cache_dir = root / "images"
        self.json_cache_dir.mkdir(parents=True, exist_ok=True)
        self.image_cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self._inflight_lock = threading.Lock()
        # One map for every kind of in-flight work; keys are namespaced
        # ("json:<hash>", "img:<url>") so unrelated requests cannot collide.
        self._inflight: dict[str, Future[Any]] = {}

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
        with self._inflight_lock:
            self._inflight.clear()
        self.session.close()

    # -- request coalescing -------------------------------------------------

    def _coalesce[T](self, key: str, factory: Callable[[], T]) -> T:
        """Run `factory` once for `key`, sharing the result with concurrent callers."""
        with self._inflight_lock:
            pending: Future[T] | None = self._inflight.get(key)
            future: Future[T] = pending if pending is not None else Future()
            if pending is None:
                self._inflight[key] = future
        if pending is not None:
            # Another caller owns this key; wait on its result rather than
            # duplicating the work.
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

    # -- disk-cached requests ----------------------------------------------

    @staticmethod
    def _cache_name(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _json_cache_path(self, cache_key: str) -> Path:
        return self.json_cache_dir / f"{self._cache_name(cache_key)}.json"

    def _image_cache_path(self, url: str) -> Path:
        extension = Path(url.split("?", 1)[0]).suffix.lower() or ".img"
        if len(extension) > MAX_EXTENSION_LENGTH or not extension[1:].isalnum():
            extension = ".img"
        return self.image_cache_dir / f"{self._cache_name(url)}{extension}"

    def request_json(self, url: str) -> JSONValue:
        return self._request_json_cached(url, lambda: self.session.get(url, timeout=20))

    def request_json_post(self, url: str, payload: Mapping[str, str | int | float | bool | None]) -> JSONValue:
        payload_key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        cache_key = f"POST {url}\n{payload_key}"
        return self._request_json_cached(cache_key, lambda: self.session.post(url, json=payload, timeout=20))

    def _request_json_cached(self, cache_key: str, request: Callable[[], requests.Response]) -> JSONValue:
        cache_path = self._json_cache_path(cache_key)
        if cache_path.exists():
            return self._read_json_cache(cache_path)

        def fetch() -> JSONValue:
            if cache_path.exists():
                return self._read_json_cache(cache_path)
            response = request()
            response.raise_for_status()
            data: JSONValue = response.json()
            with cache_path.open("w", encoding="utf-8") as cache_file:
                json.dump(data, cache_file)
            return data

        return self._coalesce(f"json:{self._cache_name(cache_key)}", fetch)

    @staticmethod
    def _read_json_cache(cache_path: Path) -> JSONValue:
        with cache_path.open("r", encoding="utf-8") as cache_file:
            data: JSONValue = json.load(cache_file)
        return data

    def get_image(self, url: str) -> Image.Image:
        cache_path = self._image_cache_path(url)
        if cache_path.exists():
            return self._read_image_cache(cache_path)

        def fetch() -> Image.Image:
            if not cache_path.exists():
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                cache_path.write_bytes(response.content)
            return self._read_image_cache(cache_path)

        return self._coalesce(f"img:{url}", fetch)

    @staticmethod
    def _read_image_cache(cache_path: Path) -> Image.Image:
        with cache_path.open("rb") as image_file:
            image = Image.open(io.BytesIO(image_file.read())).convert("RGBA")
        if image.width > image.height:
            image = image.rotate(90, expand=True)
        return image

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
        for cache_file in self.json_cache_dir.glob("*.json"):
            cache_file.unlink()

    def clear_image_cache(self) -> None:
        for cache_file in self.image_cache_dir.iterdir():
            if cache_file.is_file():
                cache_file.unlink()
