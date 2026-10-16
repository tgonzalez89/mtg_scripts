"""Scryfall-native records that do not depend on the Print Picker UI model."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

type ProgressCallback = Callable[[str, int, int], None]


@dataclass(frozen=True, slots=True)
class ScryfallCardFace:
    name: str
    image_url: str | None = None
    image_url_hq: str | None = None


@dataclass(frozen=True, slots=True)
class ScryfallCard:
    print_id: str
    oracle_id: str
    name: str
    set_code: str
    set_name: str
    set_type: str
    games: frozenset[str]
    collector_number: str
    released_on: str
    finishes: frozenset[str]
    is_default_print: bool
    is_token: bool
    faces: tuple[ScryfallCardFace, ...]
    oracle_text: str
    color_identity: frozenset[str]
    commander_legal: bool
    type_line: str
    mana_cost: str
    mana_value: float | None
    power: str | None
    toughness: str | None
    prices: dict[str, str | None]


@dataclass(frozen=True, slots=True)
class ScryfallNameMatch:
    kind: int
    card: ScryfallCard


@dataclass(frozen=True, slots=True)
class ScryfallSearchResult:
    cards: tuple[ScryfallCard, ...]
    fetched_at: float
    stale: bool = False
