from __future__ import annotations

from typing import TYPE_CHECKING

from mtg_scripts.print_picker import print_picker

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_cache_dir_option_is_forwarded_to_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    received: list[Path | None] = []

    class StubApp:
        def __init__(self, cache_dir: Path | None = None) -> None:
            received.append(cache_dir)

        def mainloop(self) -> None:
            return None

    monkeypatch.setattr(print_picker, "App", StubApp)
    assert print_picker.main(["--cache-dir", str(tmp_path)]) == 0
    assert received == [tmp_path]
