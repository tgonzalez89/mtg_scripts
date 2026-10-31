"""Parse the subset of Scryfall search syntax that the local card database can answer exactly."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .models import ScryfallCard

PRICE_ORDERS: Final = frozenset({"usd", "eur", "tix"})
_ORDERS: Final = PRICE_ORDERS | {"cmc", "name", "released"}
_DIRECTIONS: Final = frozenset({"asc", "desc", "auto"})
_UNIQUES: Final = frozenset({"cards", "prints"})
_GAMES: Final = frozenset({"paper", "arena", "mtgo"})
_COLOR_LETTERS: Final = frozenset("wubrg")
_IS_LAYOUTS: Final = {"mdfc": "modal_dfc", "split": "split", "flip": "flip", "transform": "transform"}
_TOKEN_PATTERN: Final = re.compile(r'(?:[^\s"]|"[^"]*")+')
_TERM_PATTERN: Final = re.compile(
    r"(?P<neg>-)?(?:!(?P<exact>.+)|(?P<key>[a-z]+):(?P<value>.+))",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Term:
    field: str
    value: str = ""
    negated: bool = False


@dataclass(frozen=True, slots=True)
class LocalQuery:
    terms: tuple[Term, ...]
    order: str | None = None
    direction: str = "auto"
    unique: str = "cards"


def parse_local_query(
    query: str,
    *,
    order: str | None = None,
    direction: str | None = None,
    unique: str | None = None,
) -> LocalQuery | None:
    """Return a local plan, or `None` when any part of the query needs the Scryfall API."""
    if query.count('"') % 2 or re.search(r"(?:^|\s)or(?:\s|$)", query, re.IGNORECASE) or "-(" in query:
        return None
    options: dict[str, str] = {}
    terms: list[Term] = []
    for raw_token in _TOKEN_PATTERN.findall(query):
        token = raw_token.removeprefix("(").removesuffix(")")
        if token == "":
            continue
        match = _TERM_PATTERN.fullmatch(token)
        if match is None:
            return None
        negated = match["neg"] is not None
        if match["exact"] is not None:
            terms.append(Term("exact_name", _unquote(match["exact"]), negated))
            continue
        key, value = match["key"].casefold(), _unquote(match["value"])
        if key in {"order", "dir", "unique"}:
            if negated:
                return None
            options[key] = value.casefold()
            continue
        term = _term(key, value, negated=negated)
        if term is None:
            return None
        terms.append(term)
    resolved_order = order if order is not None else options.get("order")
    resolved_direction = direction if direction is not None else options.get("dir", "auto")
    resolved_unique = unique if unique is not None else options.get("unique", "cards")
    if (
        (resolved_order is not None and resolved_order not in _ORDERS)
        or resolved_direction not in _DIRECTIONS
        or resolved_unique not in _UNIQUES
    ):
        return None
    return LocalQuery(tuple(terms), resolved_order, resolved_direction, resolved_unique)


def _unquote(value: str) -> str:
    return value[1:-1] if len(value) >= 2 and value.startswith('"') and value.endswith('"') else value  # noqa: PLR2004


def _term(key: str, value: str, *, negated: bool) -> Term | None:  # noqa: C901, PLR0911
    folded = value.casefold()
    if folded == "":
        return None
    match key:
        case "game" if folded in _GAMES:
            return Term("game", folded, negated)
        case "legal" | "f" | "format" if folded == "commander":
            return Term("commander_legal", "", negated)
        case "t" | "type":
            return Term("type", folded, negated)
        case "o" | "oracle" if "~" not in folded:
            return Term("oracle", folded, negated)
        case "otag" | "oracletag" | "function":
            return Term("otag", folded, negated)
        case "is" if folded in _IS_LAYOUTS:
            return Term("layout", _IS_LAYOUTS[folded], negated)
        case "is" if folded == "vanilla":
            return Term("vanilla", "", negated)
        case "produces" if folded in {"m", "multicolor"}:
            return Term("produces_multicolor", "", negated)
        case "produces" if len(folded) == 1 and folded in _COLOR_LETTERS | {"c"}:
            return Term("produces", folded, negated)
        case "id" | "identity" | "ci" | "commander" if set(folded) <= _COLOR_LETTERS or folded == "c":
            return Term("identity_within", "" if folded == "c" else folded, negated)
        case _:
            return None


def card_price(card: ScryfallCard, source: str) -> float | None:
    """Return the printing's price in `source`, falling back to its cheapest finish."""
    direct = card.prices.get(source)
    if direct is not None:
        return float(direct)
    finishes = [float(price) for name, price in card.prices.items() if name.startswith(source) and price is not None]
    return min(finishes, default=None)


def select_results(cards: Iterable[ScryfallCard], query: LocalQuery) -> list[ScryfallCard]:
    """Collapse printings per `unique` and sort them like Scryfall would."""
    price_source = query.order if query.order in PRICE_ORDERS else None
    if query.unique == "prints":
        chosen = list(cards)
    else:
        by_oracle: dict[str, ScryfallCard] = {}
        for card in cards:
            current = by_oracle.get(card.oracle_id)
            if current is None or _is_better_representative(card, current, price_source):
                by_oracle[card.oracle_id] = card
        chosen = list(by_oracle.values())
    return _sorted(chosen, query)


def _is_better_representative(candidate: ScryfallCard, current: ScryfallCard, price_source: str | None) -> bool:
    if price_source is not None:
        # Cheapest priced printing wins: budget tools care about the cheapest copy available.
        candidate_price = card_price(candidate, price_source)
        current_price = card_price(current, price_source)
        if candidate_price is None:
            return False
        return current_price is None or candidate_price < current_price
    return candidate.is_default_print and not current.is_default_print


def _sorted(cards: list[ScryfallCard], query: LocalQuery) -> list[ScryfallCard]:
    order = query.order or "name"
    descending = query.direction == "desc" or (query.direction == "auto" and order == "released")
    present: list[tuple[float | str, ScryfallCard]] = []
    missing: list[ScryfallCard] = []
    for card in cards:
        key = _sort_value(card, order)
        if key is None:
            missing.append(card)
        else:
            present.append((key, card))
    present.sort(key=lambda item: (item[0], item[1].name.casefold()), reverse=descending)
    missing.sort(key=lambda card: card.name.casefold())
    return [card for _, card in present] + missing


def _sort_value(card: ScryfallCard, order: str) -> float | str | None:
    if order in PRICE_ORDERS:
        return card_price(card, order)
    if order == "cmc":
        return card.mana_value
    if order == "released":
        return card.released_on
    return card.name.casefold()
