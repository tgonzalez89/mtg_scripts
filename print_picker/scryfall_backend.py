import hashlib
import io
import json
from pathlib import Path
from urllib.parse import quote_plus

import requests
from PIL import Image

SCRYFALL_SEARCH_URL = "https://api.scryfall.com/cards/search?q="
USER_AGENT = "mtg-print-picker/1.0 (contact: local)"


class ScryfallBackend:
    def __init__(self, cache_dir=None, session=None):
        root = Path(cache_dir or Path(__file__).with_name(".cache"))
        self.json_cache_dir = root / "json"
        self.image_cache_dir = root / "images"
        self.json_cache_dir.mkdir(parents=True, exist_ok=True)
        self.image_cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

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

    def search_card(self, name):
        url = SCRYFALL_SEARCH_URL + quote_plus(f'!"{name}"')
        data = self.request_json(url)
        cards = data.get("data", [])
        return cards[0] if cards else None

    def get_printings(self, oracle_id):
        if not oracle_id:
            return []
        url = SCRYFALL_SEARCH_URL + quote_plus(f"unique:prints oracleid:{oracle_id}")
        printings = []
        while url:
            data = self.request_json(url)
            printings.extend(data.get("data", []))
            url = data.get("next_page") if data.get("has_more") else None
        return printings

    def get_image(self, url):
        cache_path = self._image_cache_path(url)
        if not cache_path.exists():
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            cache_path.write_bytes(response.content)
        with cache_path.open("rb") as image_file:
            return Image.open(io.BytesIO(image_file.read())).convert("RGBA")

    def clear_json_cache(self):
        for cache_file in self.json_cache_dir.glob("*.json"):
            cache_file.unlink()

    def clear_image_cache(self):
        for cache_file in self.image_cache_dir.iterdir():
            if cache_file.is_file():
                cache_file.unlink()

    @staticmethod
    def image_url(card):
        urls = ScryfallBackend.image_urls(card)
        return urls[0] if urls else None

    @staticmethod
    def image_urls(card):
        image_uris = card.get("image_uris", {})
        if image_uris.get("png"):
            return [image_uris["png"]]
        urls = []
        for face in card.get("card_faces") or []:
            face_url = face.get("image_uris", {}).get("png")
            if face_url:
                urls.append(face_url)
        return urls
