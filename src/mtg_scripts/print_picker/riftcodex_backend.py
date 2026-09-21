import re
from typing import TYPE_CHECKING, Final, TypedDict, cast
from urllib.parse import quote_plus

from .card_backend import CardBackend, CardItem, CardRecord, ProgressCallback

if TYPE_CHECKING:
    from pathlib import Path

    import requests

RIFTCODEX_SEARCH_URL: Final[str] = "https://api.riftcodex.com/cards/name?exact="
RIFTCODEX_FUZZY_SEARCH_URL: Final[str] = "https://api.riftcodex.com/cards/name?fuzzy="
USER_AGENT: Final[str] = "mtg-print-picker/1.0 (RiftCodex)"


class _RiftCodexSetResponse(TypedDict, total=False):
    """Fields used from the RiftCodex `/sets/set-id/{id}` response."""

    published_on: str


class _RiftCodexSearchResponse(TypedDict, total=False):
    """Fields used from the RiftCodex `/cards/name` search responses."""

    items: list[CardRecord]


class RiftCodexBackend(CardBackend):
    @property
    def user_agent(self) -> str:
        return USER_AGENT

    def __init__(self, cache_dir: str | Path | None = None, session: requests.Session | None = None) -> None:
        super().__init__(cache_dir, session)
        self._set_release_dates: dict[str, str] = {}

    def _release_date(self, set_code: str) -> str:
        set_code = set_code.casefold()
        if set_code not in self._set_release_dates:
            data = cast("_RiftCodexSetResponse", self.request_json(f"https://api.riftcodex.com/sets/set-id/{set_code}"))
            self._set_release_dates[set_code] = data.get("published_on", "")
        return self._set_release_dates[set_code]

    @staticmethod
    def parse_card_line(line: str) -> CardItem:
        quantity_match = re.match(r"^(\d+)\s+(.+)$", line.strip())
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        card_text = quantity_match.group(2).strip() if quantity_match else line.strip()
        match = re.match(r"^(.+?)\s+\(([A-Za-z0-9]+-\d+)\)$", card_text)
        if match:
            name, riftbound_id = match.groups()
            return {
                "quantity": quantity,
                "name": name.strip(),
                "printing_hint": {"riftbound_id": riftbound_id.lower()},
            }
        return {"quantity": quantity, "name": card_text}

    def search_card(self, name: str, printing_hint: CardRecord | None = None) -> CardRecord | None:
        cards = self._search_by_name(name)
        if printing_hint and printing_hint.get("riftbound_id"):
            requested_id = printing_hint["riftbound_id"].casefold()
            card = next(
                (card for card in cards if str(card.get("riftbound_id", "")).casefold().startswith(f"{requested_id}-")),
                None,
            )
        else:
            card = cards[0] if cards else None
        return self._annotate_release_date(card)

    def _annotate_release_date(self, card: CardRecord | None) -> CardRecord | None:
        if card:
            set_info = card.get("set") or {}
            set_code = set_info.get("set_id", "") if isinstance(set_info, dict) else str(set_info)
            card["_release_date"] = self._release_date(set_code)
        return card

    def _search_by_name(self, name: str) -> list[CardRecord]:
        normalized_name = self._normalize_name(name)
        url = RIFTCODEX_SEARCH_URL + quote_plus(normalized_name)
        data = cast("_RiftCodexSearchResponse", self.request_json(url))
        return data.get("items", [])

    def _search_by_name_fuzzy(self, name: str) -> list[CardRecord]:
        normalized_name = self._normalize_name(name)
        url = RIFTCODEX_FUZZY_SEARCH_URL + quote_plus(normalized_name)
        data = cast("_RiftCodexSearchResponse", self.request_json(url))
        return data.get("items", [])

    @staticmethod
    def _normalize_name(name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", " ", name).strip().lower()

    def _printing_names(self, card: CardRecord) -> list[str]:
        """Return distinct normalized names used to search a card."""
        names: list[str] = []
        seen_names: set[str] = set()
        for name in (card.get("name", ""), card.get("metadata", {}).get("clean_name", "")):
            normalized_name = self._normalize_name(name)
            if normalized_name and normalized_name not in seen_names:
                seen_names.add(normalized_name)
                names.append(str(name))
        return names

    def _exact_printings(self, names: list[str]) -> tuple[list[CardRecord], set[str]]:
        """Collect exact printings and their normalized base names."""
        exact_candidates: list[CardRecord] = []
        for name in names:
            if not name:
                continue
            exact_candidates.extend(self._search_by_name(name))
        base_names: set[str] = set()
        for printing in exact_candidates:
            printing_name = printing.get("name", "")
            base_names.add(printing_name.casefold())
            base_names.add(re.sub(r"\s*\([^)]*\)$", "", printing_name).casefold())
        return exact_candidates, base_names

    def get_printings(self, card: CardRecord, _progress_callback: ProgressCallback | None = None) -> list[CardRecord]:
        """Return exact and fuzzy printings associated with a RiftBound card."""
        if not isinstance(card, dict):
            return []
        names = self._printing_names(card)
        exact_candidates, base_names = self._exact_printings(names)
        printings: dict[str | None, CardRecord | None] = {}
        for printing in exact_candidates:
            printings[printing.get("id")] = self._annotate_release_date(printing)
        for name in names:
            if not name:
                continue
            for printing in self._search_by_name_fuzzy(name):
                printing_name = printing.get("name", "").casefold()
                if any(printing_name.startswith(base_name) for base_name in base_names):
                    printings[printing.get("id")] = self._annotate_release_date(printing)
        # Every value was produced by annotating a non-empty `printing` dict, so
        # `_annotate_release_date` (which only returns None for a falsy input) never
        # actually stores None here.
        return cast("list[CardRecord]", list(printings.values()))

    def card_sort_fields(self, card: CardRecord) -> tuple[str, str, str, str]:
        set_info = card.get("set") or {}
        set_code = set_info.get("set_id", "") if isinstance(set_info, dict) else str(set_info)
        return (
            card.get("name", ""),
            card.get("_release_date") or self._release_date(set_code),
            set_code,
            card.get("collector_number", ""),
        )

    @staticmethod
    def card_name(card: CardRecord) -> str:
        return card.get("name", "")

    @staticmethod
    def printing_display_name(card: CardRecord) -> str:
        set_info = card.get("set") or {}
        if isinstance(set_info, dict):
            set_label = set_info.get("label", "")
            set_id = set_info.get("set_id", "")
        else:
            set_label = ""
            set_id = str(set_info)
        return f"{set_label} ({set_id.upper()}) #{card.get('collector_number', '')}"

    @staticmethod
    def printing_export_fields(card: CardRecord, printing_hint: CardRecord | None = None) -> tuple[str, str]:
        _ = printing_hint
        set_info = card.get("set") or {}
        set_code = set_info.get("set_id", "") if isinstance(set_info, dict) else str(set_info)
        return set_code, str(card.get("collector_number", ""))

    @staticmethod
    def image_url(card: CardRecord, *, high_quality: bool = False) -> str | None:
        _ = high_quality
        media = card.get("media") or {}
        if isinstance(media, dict):
            image_url = media.get("image_url")
            if image_url:
                return image_url
        return card.get("image_url")
