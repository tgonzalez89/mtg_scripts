import hashlib
import io
import json
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image


class CardBackend(ABC):
    def __init__(self, cache_dir=None, session=None):
        root = Path(cache_dir or Path(__file__).with_name(".cache"))
        self.json_cache_dir = root / "json"
        self.image_cache_dir = root / "images"
        self.json_cache_dir.mkdir(parents=True, exist_ok=True)
        self.image_cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    @property
    @abstractmethod
    def user_agent(self):
        """Return the User-Agent value used for API and image requests."""

    @staticmethod
    def _cache_name(url):
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _json_cache_path(self, url):
        return self.json_cache_dir / f"{self._cache_name(url)}.json"

    def _image_cache_path(self, url):
        extension = Path(url.split("?", 1)[0]).suffix.lower() or ".img"
        if len(extension) > 5 or not extension[1:].isalnum():
            extension = ".img"
        return self.image_cache_dir / f"{self._cache_name(url)}{extension}"

    def request_json(self, url):
        cache_path = self._json_cache_path(url)
        if cache_path.exists():
            with cache_path.open("r", encoding="utf-8") as cache_file:
                return json.load(cache_file)

        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()
        with cache_path.open("w", encoding="utf-8") as cache_file:
            json.dump(data, cache_file)
        return data

    def get_image(self, url):
        cache_path = self._image_cache_path(url)
        if not cache_path.exists():
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            cache_path.write_bytes(response.content)
        with cache_path.open("rb") as image_file:
            image = Image.open(io.BytesIO(image_file.read())).convert("RGBA")
        if image.width > image.height:
            image = image.rotate(90, expand=True)
        return image

    def load_card_image(self, card, high_quality=False):
        url = self.image_url(card, high_quality)
        return self.get_image(url) if url else None

    def clear_json_cache(self):
        for cache_file in self.json_cache_dir.glob("*.json"):
            cache_file.unlink()

    def clear_image_cache(self):
        for cache_file in self.image_cache_dir.iterdir():
            if cache_file.is_file():
                cache_file.unlink()

    @abstractmethod
    def parse_card_line(self, line):
        """Parse one import line into quantity, name, and optional printing hints."""

    @abstractmethod
    def search_card(self, name, printing_hint=None):
        """Return the requested card printing, or None when no card was found."""

    @abstractmethod
    def get_printings(self, card):
        """Return the available printings for a card record."""

    @staticmethod
    @abstractmethod
    def card_name(card):
        """Return the display name for a card record."""

    def sort_items(self, items, include_name=False):
        return sorted(items, key=lambda item: self._sort_key(item, include_name))

    def _sort_key(self, item, include_name):
        card = item.get("card") or item.get("default_card") or item
        name, release_date, set_code, collector_number = self.card_sort_fields(card)
        name_key = name.casefold() if include_name else ""
        collector_key = self._collector_sort_key(collector_number)
        return name_key, self._release_sort_key(release_date), set_code.casefold(), collector_key

    @staticmethod
    def _release_sort_key(release_date):
        if not release_date:
            return float("inf")
        try:
            timestamp = datetime.fromisoformat(str(release_date).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return float("inf")
        return -timestamp

    @staticmethod
    def _collector_sort_key(collector_number):
        parts = re.findall(r"\d+|\D+", str(collector_number))
        return tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in parts)

    @staticmethod
    @abstractmethod
    def card_sort_fields(card):
        """Return name, release date, set code, and collector number for sorting."""

    @staticmethod
    @abstractmethod
    def printing_display_name(card):
        """Return a readable set and collector-number label for a printing."""

    @staticmethod
    @abstractmethod
    def printing_export_fields(card, printing_hint=None):
        """Return the set code and collector number used for export."""

    @staticmethod
    @abstractmethod
    def image_url(card, high_quality=False):
        """Return the image URL for a card at the requested quality."""
