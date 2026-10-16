"""Validated Forge automation runtime options."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TESSDATA_DIR = Path(r"C:\Program Files\Tesseract-OCR\tessdata")
TESSDATA_ENV_VAR = "MTG_SCRIPTS_TESSDATA_DIR"


@dataclass(frozen=True, slots=True)
class ForgeRunOptions:
    decks: list[str]
    min_matches: int | None
    tessdata_dir: Path


def default_tessdata_dir() -> Path:
    return Path(os.environ.get(TESSDATA_ENV_VAR, str(DEFAULT_TESSDATA_DIR)))


def validate_tessdata_dir(path: Path) -> Path:
    if not path.is_dir():
        message = f"Tesseract data directory does not exist or is not a directory: {path}"
        raise ValueError(message)
    return path
