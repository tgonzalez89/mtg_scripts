"""Plain quantity/name lists; printing hints and provider formats stay separate."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def normalize_card_name(name: str) -> str:
    """Preserve the established lowercase and first slash-separator key policy."""
    return re.sub(r"(.*?[^/]) *//? *([^/].*)", r"\1 // \2", name.strip()).lower()


def parse_card_line(line: str) -> tuple[int, str] | None:
    """Return quantity and display name without interpreting printing hints."""
    text = re.sub(r"\s+", " ", line).strip()
    if not text:
        return None
    quantity_text, separator, name = text.partition(" ")
    if separator and quantity_text.isdigit():
        return int(quantity_text), name
    return 1, text


def parse_card_list(lines: Iterable[str]) -> dict[str, int]:
    """Aggregate plain-list entries by their matching key, in input order."""
    counts: dict[str, int] = {}
    for line in lines:
        entry = parse_card_line(line)
        if entry is not None:
            quantity, name = entry
            key = normalize_card_name(name)
            counts[key] = counts.get(key, 0) + quantity
    return counts
