"""Structured JSON files with caller-controlled formatting and atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import cast

type JSONValue = bool | int | float | str | list[JSONValue] | dict[str, JSONValue] | None


def read_json(path: Path) -> JSONValue:
    with path.open(encoding="utf-8") as source:
        return cast("JSONValue", json.load(source))


def write_json(
    path: Path,
    data: object,
    *,
    indent: int | None = 2,
    sort_keys: bool = True,
    newline: str | None = None,
) -> None:
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline=newline) as destination:
            json.dump(data, destination, indent=indent, sort_keys=sort_keys)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
