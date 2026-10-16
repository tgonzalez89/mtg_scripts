"""Pure CardTrader language and chunking policies."""

from __future__ import annotations

import argparse
from typing import Final

ALLOWED_LANGS: Final[tuple[str, ...]] = tuple(
    sorted({"Any", "en", "jp", "zh-CN", "zh-TW", "ft", "de", "it", "kr", "pt", "ru", "es"})
)


def split_string_evenly(text: str, max_per_group: int = 100) -> list[list[str]]:
    lines = text.splitlines()
    if not lines:
        return []
    num_groups = -(-len(lines) // max_per_group)
    base_size = len(lines) // num_groups
    remainder = len(lines) % num_groups
    groups: list[list[str]] = []
    start = 0
    for index in range(num_groups):
        size = base_size + (1 if index < remainder else 0)
        groups.append(lines[start : start + size])
        start += size
    return groups


def parse_language_thresholds(arg_value: str) -> dict[str, int]:
    """Parse language threshold order, retaining the validated CLI contract."""
    if not arg_value:
        return {"Any": 0}
    pairs = [pair.strip() for pair in arg_value.split(",") if pair.strip()]
    if not pairs:
        message = "Can't be empty."
        raise argparse.ArgumentTypeError(message)

    thresholds: dict[str, int] = {}
    for index, pair in enumerate(pairs):
        language, threshold = _parse_language_threshold_pair(pair, index)
        if language not in ALLOWED_LANGS:
            message = f"Language '{language}' is not allowed. Allowed: {ALLOWED_LANGS}."
            raise argparse.ArgumentTypeError(message)
        if language in thresholds:
            message = f"Duplicate language '{language}' found."
            raise argparse.ArgumentTypeError(message)
        if language == "Any" and index != len(pairs) - 1:
            message = "'Any' language may only appear as the last entry."
            raise argparse.ArgumentTypeError(message)
        thresholds[language] = threshold
    return thresholds


def _parse_language_threshold_pair(pair: str, index: int) -> tuple[str, int]:
    if ":" not in pair:
        message = f"Invalid format for language:threshold '{pair}'. Expected 'lang:int'."
        raise argparse.ArgumentTypeError(message)
    language, threshold_text = (part.strip() for part in pair.split(":", 1))
    if not threshold_text.isdigit():
        message = f"Threshold for language '{language}' must be an integer (got '{threshold_text}')."
        raise argparse.ArgumentTypeError(message)
    threshold = int(threshold_text)
    if index == 0 and threshold != 0:
        message = f"The first language ('{language}') must have a threshold of 0."
        raise argparse.ArgumentTypeError(message)
    if index > 0 and threshold < 1:
        message = f"Language '{language}' must have a positive threshold (>=1)."
        raise argparse.ArgumentTypeError(message)
    return language, threshold
