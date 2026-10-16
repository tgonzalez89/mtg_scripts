from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from mtg_scripts.forge_auto_battler.forge_auto_battler import parse_arguments
from mtg_scripts.forge_auto_battler.runtime_config import TESSDATA_ENV_VAR, default_tessdata_dir, validate_tessdata_dir
from mtg_scripts.forge_auto_battler.window_session import ForgeWindowSession

if TYPE_CHECKING:
    from pathlib import Path


def test_tessdata_directory_uses_environment_override_and_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(TESSDATA_ENV_VAR, str(tmp_path))
    assert default_tessdata_dir() == tmp_path
    assert validate_tessdata_dir(tmp_path) == tmp_path
    with pytest.raises(ValueError, match="Tesseract data directory"):
        validate_tessdata_dir(tmp_path / "missing")


def test_window_session_requires_a_focused_window() -> None:
    session = ForgeWindowSession()
    with pytest.raises(RuntimeError, match="has not been focused"):
        session.require_window()
    window = object()
    session.window = window
    assert session.require_window() is window


def test_forge_cli_builds_typed_options_with_tessdata_override(tmp_path: Path) -> None:
    options = parse_arguments(["one", "two", "three", "four", "--tessdata-dir", str(tmp_path)])
    assert options.decks == ["one", "two", "three", "four"]
    assert options.tessdata_dir == tmp_path
