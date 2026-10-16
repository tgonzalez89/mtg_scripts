from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Never

import pytest

from mtg_scripts.common.json_io import read_json, write_json


@pytest.mark.parametrize(("indent", "sort_keys", "newline"), [(2, True, None), (2, False, None), (None, False, "\n")])
def test_json_bytes_preserve_formatting_policies(
    tmp_path: Path, indent: int | None, *, sort_keys: bool, newline: str | None
) -> None:
    data = {"z": [1, None], "a": "\u00f1"}
    destination = tmp_path / "payload.json"
    write_json(destination, data, indent=indent, sort_keys=sort_keys, newline=newline)
    expected = json.dumps(data, indent=indent, sort_keys=sort_keys).replace(
        "\n", os.linesep if newline is None else newline
    )
    assert destination.read_bytes() == expected.encode("utf-8")
    assert read_json(destination) == data


def test_serialization_failure_preserves_existing_file_and_removes_temporary(tmp_path: Path) -> None:
    destination = tmp_path / "payload.json"
    destination.write_text('{"original": true}', encoding="utf-8")
    with pytest.raises(TypeError):
        write_json(destination, {"invalid": object()})
    assert destination.read_text(encoding="utf-8") == '{"original": true}'
    assert list(tmp_path.iterdir()) == [destination]


def test_replace_failure_preserves_existing_file_and_removes_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "payload.json"
    write_json(destination, {"original": True})

    def fail_replace(self: Path, target: Path) -> Never:
        message = "replacement failed"
        raise OSError(message)

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        write_json(destination, {"new": True})
    assert read_json(destination) == {"original": True}
    assert list(tmp_path.iterdir()) == [destination]


def test_missing_parent_is_not_created_implicitly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        write_json(tmp_path / "missing" / "payload.json", {})
    assert not list(tmp_path.iterdir())


def test_read_rejects_corrupt_json(tmp_path: Path) -> None:
    source = tmp_path / "broken.json"
    source.write_text("{broken", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_json(source)
