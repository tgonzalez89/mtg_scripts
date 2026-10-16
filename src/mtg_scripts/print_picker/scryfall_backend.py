import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, override

from mtg_scripts.services.scryfall import ScryfallService
from mtg_scripts.services.scryfall.store import normalize_name

from .card_backend import CardBackend
from .models import CardFace, CardPrint, DeckEntry, PrintQuery, Resolution, matches_set_code

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    import requests

    from mtg_scripts.services.scryfall.models import ProgressCallback, ScryfallCard, ScryfallNameMatch
    from mtg_scripts.services.scryfall.store import CardStore

USER_AGENT: Final[str] = "mtg-print-picker/1.0 (contact: local)"

# Scryfall's own vocabulary, deliberately kept out of the shared model.
FOIL: Final[str] = "foil"
NONFOIL: Final[str] = "nonfoil"
FOIL_STAR: Final[str] = "★"
FOIL_SUFFIX: Final[str] = "*F*"

# Sets whose contents are not cards you put in a deck: Art Series and other
# memorabilia, token sheets, Unglued-style minigame cards, and oversized
# Vanguard avatars.
NONPLAYABLE_SET_TYPES: Final[frozenset[str]] = frozenset({"memorabilia", "token", "minigame", "vanguard"})

# A printing's `games` lists the platforms it exists on. Physical printings are
# what this tool is for, so they win over digital-only ones.
PAPER: Final[str] = "paper"


@dataclass(frozen=True, slots=True)
class ScryfallPrint(CardPrint):
    set_type: str = ""
    games: frozenset[str] = frozenset()
    finishes: frozenset[str] = frozenset()
    is_default_print: bool = False
    is_token: bool = False


@dataclass(frozen=True, slots=True)
class NameMatch:
    kind: int
    card: ScryfallPrint


def to_print(card: ScryfallCard) -> ScryfallPrint:
    return ScryfallPrint(
        backend="scryfall",
        print_id=card.print_id,
        card_key=card.oracle_id,
        name=card.name,
        set_code=card.set_code,
        set_name=card.set_name,
        set_type=card.set_type,
        games=card.games,
        collector_number=card.collector_number,
        released_on=card.released_on,
        finishes=card.finishes,
        faces=tuple(
            CardFace(name=face.name, image_url=face.image_url, image_url_hq=face.image_url_hq) for face in card.faces
        ),
        is_default_print=card.is_default_print,
        is_token=card.is_token,
    )


class ScryfallBackend(CardBackend):
    supports_progress = True
    cache_provider = "scryfall"

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        session: requests.Session | None = None,
        *,
        service: ScryfallService | None = None,
    ) -> None:
        super().__init__(cache_dir, session)
        self._owns_service = service is None
        self.service = service or ScryfallService(cache_dir=cache_dir, http_client=self.http)

    @property
    @override
    def user_agent(self) -> str:
        return USER_AGENT

    # -- import parsing -----------------------------------------------------

    @staticmethod
    @override
    def parse_line(line: str) -> DeckEntry:
        quantity_match = re.match(r"^(\d+)\s+(.+)$", line.strip())
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        card_text = quantity_match.group(2).strip() if quantity_match else line.strip()

        foil_match = re.search(r"\s+(\*F\*|\*|★)$", card_text)
        is_foil = True if foil_match else None
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

        return DeckEntry(
            quantity=quantity,
            name=name.strip(),
            query=PrintQuery(set_code=set_code, collector_number=collector_number, foil=is_foil),
        )

    @staticmethod
    @override
    def export_card_text(card: CardPrint, entry: DeckEntry) -> str:
        """Format as `Name (set) 123`, with a trailing `*F*` for foils."""
        raw_number = card.collector_number
        collector_number = raw_number.removesuffix(FOIL_STAR).removesuffix("*").rstrip()
        is_foil = entry.query.foil is True or raw_number != collector_number

        parts = [card.name or entry.name]
        if card.set_code:
            parts.append(f"({card.set_code})")
        if collector_number:
            parts.append(collector_number)
        if is_foil:
            parts.append(FOIL_SUFFIX)
        return " ".join(parts)

    # -- resolution ---------------------------------------------------------

    @override
    def resolve(self, entries: Sequence[DeckEntry], progress: ProgressCallback | None = None) -> list[Resolution]:
        if not entries:
            return []
        store = self._card_store(progress)
        # One query for the whole deck, rather than one per line.
        candidates = store.by_name([entry.name for entry in entries])
        resolutions = [Resolution(entry=entry, card=self._select(candidates, entry)) for entry in entries]
        self._retry_as_whole_name(store, resolutions)
        return resolutions

    def _retry_as_whole_name(self, store: CardStore, resolutions: list[Resolution]) -> None:
        """Re-read lines whose trailing number turned out not to be one.

        `Specimen 73` parses as the card "Specimen", printing 73 — but it is
        also a card name in its own right. The reading is genuinely ambiguous,
        and only a failed lookup tells us which was meant.
        """
        pending: dict[int, DeckEntry] = {}
        for index, resolution in enumerate(resolutions):
            query = resolution.entry.query
            if (
                resolution.card is None
                and query.collector_number is not None
                and query.collector_number != ""
                and query.set_code in (None, "")
            ):
                pending[index] = DeckEntry(
                    quantity=resolution.entry.quantity,
                    name=f"{resolution.entry.name} {query.collector_number}",
                    query=PrintQuery(foil=query.foil),
                )
        if not pending:
            return
        candidates = store.by_name([entry.name for entry in pending.values()])
        for index, entry in pending.items():
            card = self._select(candidates, entry)
            if card is not None:
                resolutions[index] = Resolution(entry=entry, card=card)

    def _select(self, candidates: dict[str, list[ScryfallNameMatch]], entry: DeckEntry) -> ScryfallPrint | None:
        matches = [
            NameMatch(kind=match.kind, card=to_print(match.card))
            for match in candidates.get(normalize_name(entry.name), [])
        ]
        if not entry.query:
            return _select_by_name_only(matches)
        # An explicit set or number already pins the printing, so every match
        # competes regardless of how its name matched.
        cards = [match.card for match in matches]
        identity_matches = [card for card in cards if _matches_identity(card, entry.query)]
        if not identity_matches:
            return None
        if entry.query.foil is True:
            foil_matches = [card for card in identity_matches if FOIL in card.finishes]
            return _best(foil_matches or identity_matches)
        if entry.query.foil is False:
            return _best([card for card in identity_matches if NONFOIL in card.finishes])
        nonfoil_matches = [card for card in identity_matches if NONFOIL in card.finishes]
        return _best(nonfoil_matches or identity_matches)

    @override
    def printings_of(self, card: CardPrint, progress: ProgressCallback | None = None) -> Sequence[CardPrint]:
        return tuple(to_print(printing) for printing in self._card_store(progress).printings_of(card.card_key))

    # -- store lifecycle ----------------------------------------------------

    def _card_store(self, progress: ProgressCallback | None = None, *, force_refresh: bool = False) -> CardStore:
        return self.service.get_store(progress, force_refresh=force_refresh)

    @override
    def close(self) -> None:
        if self._owns_service:
            self.service.close()
        super().close()

    @override
    def clear_json_cache(self) -> None:
        super().clear_json_cache()
        self.service.clear_search_cache()

    def refresh_database(self, progress: ProgressCallback | None = None) -> CardStore:
        """Refresh Scryfall metadata and publish a new store generation if available."""
        return self.service.refresh_bulk(progress)


def _select_by_name_only(matches: list[NameMatch]) -> ScryfallPrint | None:
    """Choose a printing for a bare card name.

    The most direct kind of name match wins outright: if the line names a
    printing's flavor name, that printing *is* what was asked for, and must not
    be traded for the plain card's default printing.
    """
    for kind in sorted({match.kind for match in matches}):
        chosen = _preferred_printing([match.card for match in matches if match.kind == kind])
        if chosen is not None:
            return chosen
    return None


def _preferred_printing(group: list[ScryfallPrint]) -> ScryfallPrint | None:
    """Pick within one match kind: Scryfall's default printing, nonfoil first."""
    # A flavor-named printing is a specific alternate-art card and so is almost
    # never the default printing, hence the fallback to the whole group.
    pool = [card for card in group if card.is_default_print] or group
    # A line with no finish requested means the ordinary version, so skip
    # foil-only printings when a nonfoil one exists.
    nonfoil = [card for card in pool if NONFOIL in card.finishes]
    return _best(nonfoil or pool)


def _matches_identity(card: ScryfallPrint, query: PrintQuery) -> bool:
    """Return whether a printing matches the set and number the line asked for."""
    if not matches_set_code(card, query):
        return False
    if query.collector_number is None or query.collector_number == "":
        return True
    actual = card.collector_number.casefold()
    requested = query.collector_number.casefold()
    # Scryfall suffixes a foil-only printing's number with a star.
    return actual in (requested, f"{requested}{FOIL_STAR}")


def _best(candidates: list[ScryfallPrint]) -> ScryfallPrint | None:
    """Pick the most likely intended printing."""
    return min(candidates, key=_preference) if candidates else None


def _preference(card: ScryfallPrint) -> tuple[bool, bool]:
    """Rank printings: real deck cards first, then physical ones. Lower is better.

    This only breaks ties. Equally-ranked printings keep the store's ordering —
    most direct name match first, then newest — and a demoted printing still
    wins when it is the only one available.
    """
    return _is_nonplayable(card), PAPER not in card.games


def _is_nonplayable(card: ScryfallPrint) -> bool:
    """Return whether a printing is a collectible rather than a deck card.

    Art Series cards (`Forest // Forest` and friends) live in `memorabilia`
    sets and match by front-face name, so without this they can win a plain
    name lookup over the real card.
    """
    return card.is_token or card.set_type in NONPLAYABLE_SET_TYPES


def _report_progress(progress: ProgressCallback | None, message: str, current: int, total: int) -> None:
    if progress:
        progress(message, current, total)
