"""Typed configuration for mana-base creation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CardFilterConfig:
    colors: str
    price_source: str
    max_price_group_average: float
    max_price_specific_lands: float
    allow_off_color_lands: bool


@dataclass(frozen=True, slots=True)
class CreatorConfig:
    colors: str
    total_lands: int
    min_basics: int
    budget: float
    max_price_group_average: float
    max_price_specific_lands: float
    price_source: str
    enable_groups: tuple[str, ...]
    disable_groups: tuple[str, ...]
    enable_specific_lands: tuple[str, ...]
    disable_specific_lands: tuple[str, ...]
    allow_off_color_lands: bool
    allow_stale_data: bool


@dataclass(frozen=True, slots=True)
class ManaBaseLimits:
    colors: str
    budget: float
    total_lands: int
    min_basics: int
