import re
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Final, TypedDict, cast
from urllib.parse import quote_plus

from .card_backend import CardBackend, ProgressCallback
from .models import CardFace, CardPrint, DeckEntry, PrintQuery, Resolution, matches_set_code

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    import requests

RIFTCODEX_SEARCH_URL: Final[str] = "https://api.riftcodex.com/cards/name?exact="
RIFTCODEX_FUZZY_SEARCH_URL: Final[str] = "https://api.riftcodex.com/cards/name?fuzzy="
RIFTCODEX_SET_URL: Final[str] = "https://api.riftcodex.com/sets/set-id/"
USER_AGENT: Final[str] = "mtg-print-picker/1.0 (RiftCodex)"
BACKEND_NAME: Final[str] = "riftcodex"

MAX_RESOLVE_WORKERS: Final[int] = 8


class _RiftCodexSetResponse(TypedDict, total=False):
    """Fields used from the RiftCodex `/sets/set-id/{id}` response."""

    published_on: str


class _RiftCodexSearchResponse(TypedDict, total=False):
    """Fields used from the RiftCodex `/cards/name` search responses."""

    items: list[dict[str, Any]]


class RiftCodexBackend(CardBackend):
    def __init__(self, cache_dir: str | Path | None = None, session: requests.Session | None = None) -> None:
        super().__init__(cache_dir, session)
        # Set code -> publication date. A handful of short strings; the API has
        # no bulk endpoint, so this avoids one request per card.
        self._set_release_dates: dict[str, str] = {}

    @property
    def user_agent(self) -> str:
        return USER_AGENT

    def close(self) -> None:
        self._set_release_dates.clear()
        super().close()

    # -- import parsing -----------------------------------------------------

    @staticmethod
    def parse_line(line: str) -> DeckEntry:
        quantity_match = re.match(r"^(\d+)\s+(.+)$", line.strip())
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        card_text = quantity_match.group(2).strip() if quantity_match else line.strip()
        # A RiftBound printing code is "<set>-<collector number>", e.g. (OGN-185).
        match = re.match(r"^(.+?)\s+\(([A-Za-z0-9]+)-(\d+)\)$", card_text)
        if match:
            name, set_code, collector_number = match.groups()
            return DeckEntry(
                quantity=quantity,
                name=name.strip(),
                query=PrintQuery(set_code=set_code.lower(), collector_number=collector_number),
            )
        return DeckEntry(quantity=quantity, name=card_text)

    @staticmethod
    def export_card_text(card: CardPrint, entry: DeckEntry) -> str:
        """Format as `Name (SET-017)`, the same printing code imports use."""
        name = card.name or entry.name
        if not (card.set_code and card.collector_number):
            return name
        return f"{name} ({card.set_code.upper()}-{card.collector_number})"

    # -- resolution ---------------------------------------------------------

    def resolve(self, entries: Sequence[DeckEntry], progress: ProgressCallback | None = None) -> list[Resolution]:
        _ = progress
        if not entries:
            return []
        with ThreadPoolExecutor(max_workers=min(MAX_RESOLVE_WORKERS, len(entries))) as executor:
            return list(executor.map(self._resolve_one, entries))

    def _resolve_one(self, entry: DeckEntry) -> Resolution:
        try:
            cards = [self._to_print(item) for item in self._search_exact(entry.name)]
        except (OSError, ValueError) as error:
            return Resolution(entry=entry, error=str(error))
        if entry.query:
            card = next((card for card in cards if _matches_identity(card, entry.query)), None)
        else:
            card = cards[0] if cards else None
        return Resolution(entry=entry, card=card)

    def printings_of(self, card: CardPrint, progress: ProgressCallback | None = None) -> Sequence[CardPrint]:
        """Return exact and fuzzy printings associated with a RiftBound card."""
        _ = progress
        names = self._printing_names(card)
        exact_items = [item for name in names for item in self._search_exact(name)]
        base_names = _base_names(exact_items)

        printings: dict[str, CardPrint] = {}
        for item in exact_items:
            printing = self._to_print(item)
            printings[printing.print_id] = printing
        for name in names:
            for item in self._search_fuzzy(name):
                item_name = str(item.get("name", "")).casefold()
                if any(item_name.startswith(base_name) for base_name in base_names):
                    printing = self._to_print(item)
                    printings[printing.print_id] = printing
        return list(printings.values())

    @staticmethod
    def _printing_names(card: CardPrint) -> list[str]:
        """Return the distinct names worth searching for a card's other printings."""
        names: list[str] = []
        seen: set[str] = set()
        for name in (card.name, card.card_key):
            normalized = _normalize_name(name)
            if normalized and normalized not in seen:
                seen.add(normalized)
                names.append(name)
        return names

    # -- API access ---------------------------------------------------------

    def _search_exact(self, name: str) -> list[dict[str, Any]]:
        return self._search(RIFTCODEX_SEARCH_URL, name)

    def _search_fuzzy(self, name: str) -> list[dict[str, Any]]:
        return self._search(RIFTCODEX_FUZZY_SEARCH_URL, name)

    def _search(self, base_url: str, name: str) -> list[dict[str, Any]]:
        normalized = _normalize_name(name)
        if not normalized:
            return []
        data = cast("_RiftCodexSearchResponse", self.request_json(base_url + quote_plus(normalized)))
        return data.get("items", [])

    def _release_date(self, set_code: str) -> str:
        set_code = set_code.casefold()
        if not set_code:
            return ""
        if set_code not in self._set_release_dates:
            data = cast("_RiftCodexSetResponse", self.request_json(RIFTCODEX_SET_URL + set_code))
            self._set_release_dates[set_code] = data.get("published_on", "")
        return self._set_release_dates[set_code]

    # -- mapping ------------------------------------------------------------

    def _to_print(self, item: dict[str, Any]) -> CardPrint:
        """Map one RiftCodex search result onto the shared domain model."""
        set_info = item.get("set") or {}
        set_code = str(set_info.get("set_id", "")) if isinstance(set_info, dict) else str(set_info)
        set_name = str(set_info.get("label", "")) if isinstance(set_info, dict) else ""
        riftbound_id = str(item.get("riftbound_id", ""))
        name = str(item.get("name", ""))
        metadata = item.get("metadata") or {}
        clean_name = str(metadata.get("clean_name", "")) if isinstance(metadata, dict) else ""
        media = item.get("media") or {}
        image_url = str(media.get("image_url", "")) if isinstance(media, dict) else ""
        image_url = image_url or str(item.get("image_url", ""))
        return CardPrint(
            backend=BACKEND_NAME,
            print_id=str(item.get("id", "")) or riftbound_id,
            # RiftCodex has no oracle identity, so the printing-independent
            # clean name is what groups a card's printings together.
            card_key=clean_name or name,
            name=name,
            set_code=set_code,
            set_name=set_name,
            collector_number=_collector_number(riftbound_id, item.get("collector_number")),
            released_on=self._release_date(set_code),
            faces=(CardFace(name=name, image_url=image_url or None, image_url_hq=image_url or None),),
        )


def _collector_number(riftbound_id: str, raw_number: object) -> str:
    """Return the collector number in the zero-padded form decklists use.

    The `collector_number` field is an unpadded integer (17), while the middle
    segment of `riftbound_id` keeps the printed form ("ogs-017-024"). Decklists
    quote the padded form, so prefer it and fall back to the raw field.
    """
    segments = riftbound_id.split("-")
    expected_segments = 3
    if len(segments) == expected_segments and segments[1].isdigit():
        return segments[1]
    return "" if raw_number is None else str(raw_number)


def _matches_identity(card: CardPrint, query: PrintQuery) -> bool:
    """Return whether a printing matches the printing code the line asked for.

    RiftCodex collector numbers are plain zero-padded digits, so unlike Scryfall
    there is no starred foil variant to tolerate.
    """
    if not matches_set_code(card, query):
        return False
    return not query.collector_number or card.collector_number == query.collector_number


def _base_names(items: list[dict[str, Any]]) -> set[str]:
    """Return the name prefixes a fuzzy match must start with to be accepted."""
    base_names: set[str] = set()
    for item in items:
        name = str(item.get("name", ""))
        base_names.add(name.casefold())
        base_names.add(re.sub(r"\s*\([^)]*\)$", "", name).casefold())
    return base_names


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", " ", name).strip().lower()
