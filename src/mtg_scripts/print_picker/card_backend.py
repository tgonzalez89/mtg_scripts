import hashlib
import io
import json
import re
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import TypedDict, cast

import requests
from PIL import Image

MAX_EXTENSION_LENGTH = 5
IMAGE_LOADING_ENABLED = True


class CardRecord(TypedDict, total=False):
    """Common fields used by card API records."""

    name: str
    set: str
    set_name: str
    collector_number: str
    release_date: str
    _release_date: str
    released_at: str
    type_line: str
    layout: str
    image_uris: dict[str, str]
    card_faces: list[CardRecord]
    metadata: dict[str, str]
    media: dict[str, str]
    image_url: str
    oracle_id: str
    flavor_name: str
    finishes: list[str]
    images: tuple[Image.Image | None, ...]
    image: Image.Image | None
    display_name: str
    error: str
    image_loading: bool
    face_index: int
    _source_item: CardItem
    riftbound_id: str


class CardItem(CardRecord, total=False):
    """Imported card item and its resolved API data."""

    quantity: int
    name: str
    card: CardRecord | None
    default_card: CardRecord | None
    chosen_print: CardRecord | None
    printing_hint: CardRecord
    images: tuple[Image.Image | None, ...]
    image: Image.Image | None
    error: str
    image_loading: bool
    display_name: str


type ProgressCallback = Callable[[str, int, int], None]
type ImagePair = tuple[Image.Image | None, ...]


class CardBackend(ABC):
    supports_progress = False

    def __init__(self, cache_dir: str | Path | None = None, session: requests.Session | None = None) -> None:
        root = Path(cache_dir or Path(__file__).with_name(".cache"))
        self.json_cache_dir = root / "json"
        self.image_cache_dir = root / "images"
        self.json_cache_dir.mkdir(parents=True, exist_ok=True)
        self.image_cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self._request_lock = threading.Lock()
        self._inflight_json = {}
        self._inflight_images = {}
        self._card_cache = {}
        self._inflight_cards = {}
        self._printing_cache = {}
        self._inflight_printings = {}

    @property
    @abstractmethod
    def user_agent(self) -> str:
        """Return the User-Agent value used for API and image requests."""

    @staticmethod
    def _cache_name(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _json_cache_path(self, url: str) -> Path:
        return self.json_cache_dir / f"{self._cache_name(url)}.json"

    def _image_cache_path(self, url: str) -> Path:
        extension = Path(url.split("?", 1)[0]).suffix.lower() or ".img"
        if len(extension) > MAX_EXTENSION_LENGTH or not extension[1:].isalnum():
            extension = ".img"
        return self.image_cache_dir / f"{self._cache_name(url)}{extension}"

    def request_json(self, url: str) -> object:
        return self._request_json_cached(
            url,
            self._json_cache_path(url),
            lambda: self.session.get(url, timeout=20),
        )

    def request_json_post(self, url: str, payload: dict[str, str | int | float | bool | None]) -> object:
        payload_key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        cache_key = f"POST {url}\n{payload_key}"
        return self._request_json_cached(
            cache_key,
            self._json_cache_path(cache_key),
            lambda: self.session.post(url, json=payload, timeout=20),
        )

    def _request_json_cached(
        self, cache_key: str, cache_path: Path, request: Callable[[], requests.Response]
    ) -> object:
        if cache_path.exists():
            with cache_path.open("r", encoding="utf-8") as cache_file:
                return json.load(cache_file)

        with self._request_lock:
            future = self._inflight_json.get(cache_key)
            if future is None:
                future = Future()
                self._inflight_json[cache_key] = future
                owner = True
            else:
                owner = False
        if not owner:
            return future.result()

        try:
            if cache_path.exists():
                with cache_path.open("r", encoding="utf-8") as cache_file:
                    data = json.load(cache_file)
            else:
                response = request()
                response.raise_for_status()
                data = response.json()
                with cache_path.open("w", encoding="utf-8") as cache_file:
                    json.dump(data, cache_file)
        except BaseException as error:
            future.set_exception(error)
            raise
        else:
            future.set_result(data)
            return data
        finally:
            with self._request_lock:
                self._inflight_json.pop(cache_key, None)

    def get_image(self, url: str) -> Image.Image:
        cache_path = self._image_cache_path(url)
        if cache_path.exists():
            return self._read_image_cache(cache_path)

        with self._request_lock:
            future = self._inflight_images.get(url)
            if future is None:
                future = Future()
                self._inflight_images[url] = future
                owner = True
            else:
                owner = False
        if not owner:
            return future.result()

        try:
            if not cache_path.exists():
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                cache_path.write_bytes(response.content)
            image = self._read_image_cache(cache_path)
        except BaseException as error:
            future.set_exception(error)
            raise
        else:
            future.set_result(image)
            return image
        finally:
            with self._request_lock:
                self._inflight_images.pop(url, None)

    @staticmethod
    def _read_image_cache(cache_path: Path) -> Image.Image:
        with cache_path.open("rb") as image_file:
            image = Image.open(io.BytesIO(image_file.read())).convert("RGBA")
        if image.width > image.height:
            image = image.rotate(90, expand=True)
        return image

    def load_card_images(self, card: CardRecord, *, high_quality: bool = False) -> ImagePair:
        if not IMAGE_LOADING_ENABLED:
            return None, None
        url = self.image_url(card, high_quality=high_quality)
        image = self.get_image(url) if url else None
        return image, None

    def lookup_card(self, name: str, printing_hint: CardRecord | None = None) -> CardRecord | None:
        key = (name, self._freeze_value(printing_hint))
        with self._request_lock:
            if key in self._card_cache:
                return self._card_cache[key]
            future = self._inflight_cards.get(key)
            if future is None:
                future = Future()
                self._inflight_cards[key] = future
                owner = True
            else:
                owner = False
        if not owner:
            return future.result()

        try:
            card = self.search_card(name, printing_hint)
            with self._request_lock:
                self._card_cache[key] = card
        except BaseException as error:
            future.set_exception(error)
            raise
        else:
            future.set_result(card)
            return card
        finally:
            with self._request_lock:
                self._inflight_cards.pop(key, None)

    def lookup_printings(self, card: CardRecord, progress_callback: ProgressCallback | None = None) -> list[CardRecord]:
        key = self._printing_cache_key(card)
        with self._request_lock:
            if key in self._printing_cache:
                return self._copy_printings(self._printing_cache[key])
            future = self._inflight_printings.get(key)
            if future is None:
                future = Future()
                self._inflight_printings[key] = future
                owner = True
            else:
                owner = False
        if not owner:
            return self._copy_printings(future.result())

        try:
            printings = self.get_printings(card, progress_callback)
            with self._request_lock:
                self._printing_cache[key] = printings
        except BaseException as error:
            future.set_exception(error)
            raise
        else:
            future.set_result(printings)
            return self._copy_printings(printings)
        finally:
            with self._request_lock:
                self._inflight_printings.pop(key, None)

    @staticmethod
    def _copy_printings(printings: list[CardRecord]) -> list[CardRecord]:
        return [printing.copy() for printing in printings]

    @staticmethod
    def _printing_cache_key(card: CardRecord) -> tuple[object, ...]:
        if card.get("id"):
            return "id", card["id"]
        if card.get("oracle_id"):
            return "oracle_id", card["oracle_id"]
        return "fields", card.get("name", ""), card.get("set", ""), card.get("collector_number", "")

    @staticmethod
    def _freeze_value(value: object) -> object:
        if isinstance(value, dict):
            return tuple(sorted((key, CardBackend._freeze_value(item)) for key, item in value.items()))
        if isinstance(value, (list, tuple)):
            return tuple(CardBackend._freeze_value(item) for item in value)
        if isinstance(value, set):
            return tuple(sorted(CardBackend._freeze_value(item) for item in value))
        return value

    def clear_json_cache(self) -> None:
        for cache_file in self.json_cache_dir.glob("*.json"):
            cache_file.unlink()
        self.release_memory()

    def release_memory(self) -> None:
        self.release_lookup_memory()

    def release_lookup_memory(self) -> None:
        with self._request_lock:
            self._card_cache.clear()
            self._printing_cache.clear()

    def clear_image_cache(self) -> None:
        for cache_file in self.image_cache_dir.iterdir():
            if cache_file.is_file():
                cache_file.unlink()

    @staticmethod
    @abstractmethod
    def parse_card_line(line: str) -> CardItem:
        """Parse one import line into quantity, name, and optional printing hints."""

    @abstractmethod
    def search_card(self, name: str, printing_hint: CardRecord | None = None) -> CardRecord | None:
        """Return the requested card printing, or None when no card was found."""

    @abstractmethod
    def get_printings(self, card: CardRecord, _progress_callback: ProgressCallback | None = None) -> list[CardRecord]:
        """Return the available printings for a card record."""
        raise NotImplementedError

    def lookup_cards(
        self, items: list[CardItem], _progress_callback: ProgressCallback | None = None
    ) -> list[tuple[CardRecord | None, Exception | None]]:
        """Resolve imported items, returning (card, error) pairs in input order."""
        if not items:
            return []
        with ThreadPoolExecutor(max_workers=min(8, len(items))) as executor:
            return list(executor.map(self._lookup_card_result, items))

    def _lookup_card_result(self, item: CardItem) -> tuple[CardRecord | None, Exception | None]:
        try:
            return self.lookup_card(item["name"], item.get("printing_hint")), None
        except (OSError, ValueError) as error:
            return None, error

    @staticmethod
    @abstractmethod
    def card_name(card: CardRecord) -> str:
        """Return the display name for a card record."""

    def sort_items(self, items: list[CardItem], *, include_name: bool = False) -> list[CardItem]:
        return sorted(items, key=lambda item: self._sort_key(item, include_name=include_name))

    def _sort_key(
        self, item: CardItem, *, include_name: bool
    ) -> tuple[str, float, str, tuple[tuple[int, int | str], ...]]:
        card = cast("CardRecord", item.get("card") or item.get("default_card") or item)
        name, release_date, set_code, collector_number = self.card_sort_fields(card)
        name_key = name.casefold() if include_name else ""
        collector_key = self._collector_sort_key(collector_number)
        return name_key, self._release_sort_key(release_date), set_code.casefold(), collector_key

    @staticmethod
    def _release_sort_key(release_date: object) -> float:
        if not release_date:
            return float("inf")
        try:
            timestamp = datetime.fromisoformat(str(release_date)).timestamp()
        except ValueError:
            return float("inf")
        return -timestamp

    @staticmethod
    def _collector_sort_key(collector_number: object) -> tuple[tuple[int, int | str], ...]:
        parts = re.findall(r"\d+|\D+", str(collector_number))
        return tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in parts)

    @staticmethod
    @abstractmethod
    def card_sort_fields(card: CardRecord) -> tuple[str, object, str, object]:
        """Return name, release date, set code, and collector number for sorting."""

    @staticmethod
    @abstractmethod
    def printing_display_name(card: CardRecord) -> str:
        """Return a readable set and collector-number label for a printing."""

    @staticmethod
    @abstractmethod
    def printing_export_fields(card: CardRecord, printing_hint: CardRecord | None = None) -> tuple[str, str]:
        """Return the set code and collector number used for export."""

    @staticmethod
    @abstractmethod
    def image_url(card: CardRecord, *, high_quality: bool = False) -> str | None:
        """Return the image URL for a card at the requested quality."""
