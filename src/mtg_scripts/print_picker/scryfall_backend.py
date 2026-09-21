import gzip
import json
import pickle
import re
import threading
import time
from typing import TYPE_CHECKING, Final, TypedDict, cast

from .card_backend import IMAGE_LOADING_ENABLED, CardBackend, CardItem, CardRecord, ImagePair, ProgressCallback

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    import requests
    from PIL import Image

SCRYFALL_BULK_DATA_URL: Final[str] = "https://api.scryfall.com/bulk-data"
SCRYFALL_BULK_TYPES: Final[tuple[str, str]] = ("oracle_cards", "default_cards")
SCRYFALL_BULK_METADATA_MAX_AGE: Final[int] = 24 * 60 * 60
SCRYFALL_INDEX_CACHE_VERSION: Final[int] = 2
USER_AGENT: Final[str] = "mtg-print-picker/1.0 (contact: local)"


class _ScryfallBulkDataEntry(TypedDict, total=False):
    """Fields used from a Scryfall `/bulk-data` entry."""

    type: str
    jsonl_download_uri: str
    updated_at: str


class _ScryfallBulkDataResponse(TypedDict, total=False):
    """Shape of the Scryfall `/bulk-data` list response."""

    data: list[_ScryfallBulkDataEntry]


class CardIndex(TypedDict):
    """Lookup tables built from the combined Scryfall bulk-data card index."""

    by_name: dict[str, list[CardRecord]]
    by_front_face_name: dict[str, list[CardRecord]]
    by_flavor_name: dict[str, list[CardRecord]]
    by_oracle_id: dict[str, list[CardRecord]]


class ScryfallBackend(CardBackend):
    supports_progress = True

    def __init__(self, cache_dir: str | Path | None = None, session: requests.Session | None = None) -> None:
        super().__init__(cache_dir, session)
        self.bulk_dir = self.json_cache_dir.parent / "bulk"
        self.bulk_dir.mkdir(parents=True, exist_ok=True)
        self._bulk_lock = threading.Lock()
        self._bulk_indexes: dict[str, CardIndex] = {}

    @property
    def user_agent(self) -> str:
        return USER_AGENT

    @staticmethod
    def parse_card_line(line: str) -> CardItem:
        quantity_match = re.match(r"^(\d+)\s+(.+)$", line.strip())
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        card_text = quantity_match.group(2).strip() if quantity_match else line.strip()

        foil_match = re.search(r"\s+(\*F\*|\*|Γÿà)$", card_text)
        foil_marker = foil_match.group(1) if foil_match else None
        if foil_match:
            card_text = card_text[: foil_match.start()].rstrip()

        set_and_collector_match = re.match(r"^(.+?)\s+\(([A-Za-z0-9]+)\)\s+([A-Za-z0-9][A-Za-z0-9-]*)$", card_text)
        set_match = re.match(r"^(.+?)\s+\(([A-Za-z0-9]+)\)$", card_text)
        collector_match = re.match(r"^(.+?)\s+([0-9][A-Za-z0-9-]*)$", card_text)
        if set_and_collector_match:
            name, set_code, collector_number = set_and_collector_match.groups()
        elif set_match:
            name, set_code = set_match.groups()
            collector_number = None
        elif collector_match:
            name, collector_number = collector_match.groups()
            set_code = None
        else:
            name, set_code, collector_number = card_text, None, None

        hint: CardRecord = {}
        if set_code:
            hint["set"] = set_code
        if collector_number:
            hint["collector_number"] = collector_number
        if foil_marker:
            hint["is_foil"] = True
        item: CardItem = {"quantity": quantity, "name": name.strip()}
        if hint:
            item["printing_hint"] = hint
        return item

    @staticmethod
    def _normalize_card_name(name: str) -> str:
        return re.sub(r"(?<=\S)\s*/+\s*(?=\S)", " // ", name).strip()

    @classmethod
    def _canonical_card_name(cls, name: str) -> str:
        return cls._normalize_card_name(name)

    def search_card(self, name: str, printing_hint: CardRecord | None = None) -> CardRecord | None:
        normalized_name = self._canonical_card_name(name)
        if not printing_hint:
            return self._search_unhinted_card(normalized_name)
        candidates = self._card_candidates(self._card_index(), normalized_name)
        identity_matches = [card for card in candidates if self._matches_printing_identity(card, printing_hint)]
        if not identity_matches:
            return None
        if printing_hint.get("is_foil") is True:
            foil_matches = [card for card in identity_matches if "foil" in card.get("finishes", [])]
            return self._select_card(foil_matches or identity_matches)
        if printing_hint.get("is_foil") is False:
            nonfoil_matches = [card for card in identity_matches if "nonfoil" in card.get("finishes", [])]
            return self._select_card(nonfoil_matches)
        nonfoil_matches = [card for card in identity_matches if "nonfoil" in card.get("finishes", [])]
        return self._select_card(nonfoil_matches or identity_matches)

    def _search_unhinted_card(self, normalized_name: str) -> CardRecord | None:
        index = self._card_index()
        candidates = self._default_candidates(index, normalized_name)
        if candidates:
            return self._select_card(candidates)
        candidates = self._default_candidates(index, normalized_name, include_flavor=True)
        alias_card = self._select_card(candidates)
        if not alias_card:
            return None
        oracle_id = alias_card.get("oracle_id") or next(
            (face.get("oracle_id") for face in alias_card.get("card_faces") or [] if face.get("oracle_id")),
            None,
        )
        oracle_cards = index["by_oracle_id"].get(str(oracle_id), [alias_card])
        return self._select_card(oracle_cards)

    @staticmethod
    def _matches_printing_hint(card: CardRecord, printing_hint: CardRecord) -> bool:
        if not ScryfallBackend._matches_printing_identity(card, printing_hint):
            return False
        if printing_hint.get("is_foil") is True:
            return "foil" in card.get("finishes", [])
        if printing_hint.get("is_foil") is False:
            return "nonfoil" in card.get("finishes", [])
        return True

    @staticmethod
    def _matches_printing_identity(card: CardRecord, printing_hint: CardRecord) -> bool:
        if printing_hint.get("set") and card.get("set", "").casefold() != printing_hint["set"].casefold():
            return False
        requested_number = printing_hint.get("collector_number")
        if requested_number:
            actual_number = str(card.get("collector_number", ""))
            if not ScryfallBackend._collector_number_matches(actual_number, requested_number):
                return False
        return True

    @staticmethod
    def _collector_number_matches(actual_number: str, requested_number: str) -> bool:
        requested_number = requested_number.casefold()
        actual_number = actual_number.casefold()
        if actual_number == requested_number:
            return True
        return actual_number == f"{requested_number}\u2605"

    def get_printings(self, card: CardRecord, _progress_callback: ProgressCallback | None = None) -> list[CardRecord]:
        oracle_id = card.get("oracle_id") if card else None
        if not oracle_id and card:
            oracle_id = next(
                (face.get("oracle_id") for face in card.get("card_faces") or [] if face.get("oracle_id")),
                None,
            )
        if not oracle_id:
            return []
        return self._card_index(_progress_callback)["by_oracle_id"].get(oracle_id, [])

    def lookup_cards(
        self, items: Sequence[CardItem], _progress_callback: ProgressCallback | None = None
    ) -> list[tuple[CardRecord | None, Exception | None]]:
        self._card_index(_progress_callback)
        return [self._lookup_card_result(item) for item in items]

    def clear_json_cache(self) -> None:
        super().clear_json_cache()
        with self._bulk_lock:
            self._bulk_indexes.clear()
            for bulk_file in self.bulk_dir.iterdir():
                if bulk_file.is_file():
                    bulk_file.unlink()

    def release_memory(self) -> None:
        super().release_memory()
        with self._bulk_lock:
            self._bulk_indexes.clear()

    def _card_index(self, progress_callback: ProgressCallback | None = None) -> CardIndex:
        with self._bulk_lock:
            if "cards" in self._bulk_indexes:
                return self._bulk_indexes["cards"]

            metadata = self._load_bulk_metadata()
            download_uris = [str(metadata[bulk_type]["jsonl_download_uri"]) for bulk_type in SCRYFALL_BULK_TYPES]
            version = self._cache_name("\n".join(download_uris))[:16]
            index_path = self.bulk_dir / f"cards-{version}-v{SCRYFALL_INDEX_CACHE_VERSION}.pickle"
            if index_path.exists():
                try:
                    with index_path.open("rb") as index_file:
                        index = pickle.load(index_file)  # noqa: S301 - this is an application-owned cache
                except EOFError, OSError, pickle.PickleError, ValueError:
                    index_path.unlink(missing_ok=True)
                else:
                    self._bulk_indexes["cards"] = index
                    return index
            bulk_paths: list[Path] = []
            for bulk_type, download_uri in zip(SCRYFALL_BULK_TYPES, download_uris, strict=True):
                bulk_version = self._cache_name(download_uri)[:16]
                bulk_path = self.bulk_dir / f"{bulk_type}-{bulk_version}.jsonl.gz"
                if not bulk_path.exists():
                    self._download_bulk_file(download_uri, bulk_path, progress_callback)
                bulk_paths.append(bulk_path)
            self._report_progress(progress_callback, "Building combined card index...", 0, 0)
            index = self._build_combined_index(bulk_paths[0], bulk_paths[1])
            temporary_index_path = index_path.with_suffix(index_path.suffix + ".tmp")
            with temporary_index_path.open("wb") as index_file:
                pickle.dump(index, index_file, protocol=pickle.HIGHEST_PROTOCOL)
            temporary_index_path.replace(index_path)
            self._bulk_indexes["cards"] = index
            return index

    def _load_bulk_metadata(self) -> dict[str, _ScryfallBulkDataEntry]:
        metadata_path = self.bulk_dir / "metadata.json"
        metadata_is_current = metadata_path.exists() and (
            time.time() - metadata_path.stat().st_mtime < SCRYFALL_BULK_METADATA_MAX_AGE
        )
        if metadata_is_current:
            with metadata_path.open("r", encoding="utf-8") as metadata_file:
                metadata: dict[str, _ScryfallBulkDataEntry] = json.load(metadata_file)
            if all(bulk_type in metadata for bulk_type in SCRYFALL_BULK_TYPES):
                return metadata

        response = self.session.get(SCRYFALL_BULK_DATA_URL, timeout=20)
        response.raise_for_status()
        bulk_data_response = cast("_ScryfallBulkDataResponse", response.json())
        metadata = {entry["type"]: entry for entry in bulk_data_response.get("data", [])}
        missing_types = [bulk_type for bulk_type in SCRYFALL_BULK_TYPES if bulk_type not in metadata]
        if missing_types:
            msg = f"Scryfall bulk data is missing: {', '.join(missing_types)}"
            raise ValueError(msg)
        with metadata_path.open("w", encoding="utf-8") as metadata_file:
            json.dump(metadata, metadata_file)
        return metadata

    def _download_bulk_file(
        self, url: str, destination: Path, progress_callback: ProgressCallback | None = None
    ) -> None:
        temporary_path = destination.with_suffix(destination.suffix + ".tmp")
        response = self.session.get(url, timeout=120, stream=True)
        response.raise_for_status()
        try:
            total = int(response.headers.get("content-length", 0)) if hasattr(response, "headers") else 0
            downloaded = 0
            self._report_progress(progress_callback, f"Downloading {destination.stem}...", downloaded, total)
            with temporary_path.open("wb") as output_file:
                if hasattr(response, "iter_content"):
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output_file.write(chunk)
                            downloaded += len(chunk)
                            self._report_progress(
                                progress_callback, f"Downloading {destination.stem}...", downloaded, total
                            )
                else:
                    output_file.write(response.content)
                    downloaded = len(response.content)
                    self._report_progress(progress_callback, f"Downloading {destination.stem}...", downloaded, total)
            temporary_path.replace(destination)
        finally:
            close = getattr(response, "close", None)
            if close:
                close()
            if temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _report_progress(progress_callback: ProgressCallback | None, message: str, current: int, total: int) -> None:
        if progress_callback:
            progress_callback(message, current, total)

    def _build_combined_index(self, oracle_path: Path, default_path: Path) -> CardIndex:
        default_ids: set[str] = set()
        with gzip.open(oracle_path, "rt", encoding="utf-8") as oracle_file:
            for line in oracle_file:
                card = cast("CardRecord", json.loads(line))
                if card.get("id"):
                    default_ids.add(card["id"])

        by_name: dict[str, list[CardRecord]] = {}
        by_front_face_name: dict[str, list[CardRecord]] = {}
        by_flavor_name: dict[str, list[CardRecord]] = {}
        by_oracle_id: dict[str, list[CardRecord]] = {}
        with gzip.open(default_path, "rt", encoding="utf-8") as bulk_file:
            for line in bulk_file:
                card = cast("CardRecord", json.loads(line))
                is_default = card.get("id") in default_ids
                if is_default:
                    card["_is_default"] = True
                normalized_name = self._normalize_card_name(self.card_name(card)).casefold()
                by_name.setdefault(normalized_name, []).append(card)
                first_face = (card.get("card_faces") or [{}])[0]
                front_face_name = first_face.get("name")
                if front_face_name:
                    normalized_front_name = self._normalize_card_name(front_face_name).casefold()
                    by_front_face_name.setdefault(normalized_front_name, []).append(card)
                flavor_names = [card.get("flavor_name")]
                flavor_names.extend(face.get("flavor_name") for face in card.get("card_faces") or [])
                for flavor_name in filter(None, flavor_names):
                    normalized_flavor_name = self._normalize_card_name(flavor_name).casefold()
                    by_flavor_name.setdefault(normalized_flavor_name, []).append(card)
                oracle_ids = [card.get("oracle_id")]
                oracle_ids.extend(face.get("oracle_id") for face in card.get("card_faces") or [])
                for oracle_id in dict.fromkeys(filter(None, oracle_ids)):
                    by_oracle_id.setdefault(oracle_id, []).append(card)
        return {
            "by_name": by_name,
            "by_front_face_name": by_front_face_name,
            "by_flavor_name": by_flavor_name,
            "by_oracle_id": by_oracle_id,
        }

    def _default_candidates(self, index: CardIndex, name: str, *, include_flavor: bool = False) -> list[CardRecord]:
        candidates = self._card_candidates(index, name, include_flavor=include_flavor)
        return [candidate for candidate in candidates if candidate.get("_is_default")]

    def _card_candidates(self, index: CardIndex, name: str, *, include_flavor: bool = True) -> list[CardRecord]:
        normalized_name = self._normalize_card_name(name).casefold()
        candidates: list[CardRecord] = []
        for candidate_group in (
            index["by_name"].get(normalized_name, []),
            index["by_front_face_name"].get(normalized_name, []),
            index["by_flavor_name"].get(normalized_name, []) if include_flavor else [],
        ):
            candidates.extend(candidate_group)
        unique_candidates: dict[str | int, CardRecord] = {}
        for candidate in candidates:
            candidate_id = candidate.get("id") or id(candidate)
            unique_candidates[candidate_id] = candidate
        return list(unique_candidates.values())

    @staticmethod
    def _select_card(candidates: list[CardRecord]) -> CardRecord | None:
        return min(candidates, key=ScryfallBackend._is_token) if candidates else None

    @staticmethod
    def _is_token(card: CardRecord) -> bool:
        return card.get("layout") in {"token", "double_faced_token"} or card.get("type_line", "").startswith("Token")

    @staticmethod
    def card_sort_fields(card: CardRecord) -> tuple[str, str, str, str]:
        return (
            card.get("name", ""),
            card.get("released_at", ""),
            card.get("set", ""),
            card.get("collector_number", ""),
        )

    @staticmethod
    def card_name(card: CardRecord) -> str:
        return card.get("name", "")

    @staticmethod
    def printing_display_name(card: CardRecord) -> str:
        set_name = card.get("set_name", "")
        set_code = card.get("set", "").upper()
        return f"{set_name} ({set_code}) #{card.get('collector_number', '')}"

    @staticmethod
    def printing_export_fields(card: CardRecord, printing_hint: CardRecord | None = None) -> tuple[str, str]:
        set_code = card.get("set", "")
        collector_number = ScryfallBackend._format_collector_number(
            card.get("collector_number", ""),
            foil_requested=printing_hint.get("is_foil") if printing_hint else None,
        )
        return set_code, collector_number

    @staticmethod
    def _format_collector_number(collector_number: str, *, foil_requested: bool | None = None) -> str:
        foil_star = chr(0x2605)
        if (foil_requested is True or collector_number.endswith(("*", foil_star))) and not collector_number.endswith(
            "*F*"
        ):
            base_number = (
                collector_number[:-1].rstrip()
                if collector_number.endswith(("*", foil_star))
                else collector_number.rstrip()
            )
            return f"{base_number} *F*"
        return collector_number

    @staticmethod
    def image_url(card: CardRecord, *, high_quality: bool = False) -> str | None:
        quality = "png" if high_quality else "normal"
        image_uris = card.get("image_uris", {})
        if image_uris.get(quality):
            return image_uris[quality]
        for face in card.get("card_faces") or []:
            face_url = face.get("image_uris", {}).get(quality)
            if face_url:
                return face_url
        return None

    def load_card_images(self, card: CardRecord, *, high_quality: bool = False) -> ImagePair:
        if not IMAGE_LOADING_ENABLED:
            return None, None
        if card.get("image_uris"):
            return super().load_card_images(card, high_quality=high_quality)
        images: list[Image.Image | None] = []
        for face in (card.get("card_faces") or [])[:2]:
            url = self.image_url(face, high_quality=high_quality)
            images.append(self.get_image(url) if url else None)
        images.extend([None] * (2 - len(images)))
        return tuple(images)
