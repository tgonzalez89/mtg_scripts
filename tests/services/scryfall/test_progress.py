from __future__ import annotations

import io
from typing import override

from mtg_scripts.services.scryfall.progress import TerminalProgressIndicator


class _Tty(io.StringIO):
    @override
    def isatty(self) -> bool:
        return True


def test_terminal_indicator_draws_bar_speed_and_source_in_place() -> None:
    now = [0.0]
    stream = _Tty()
    indicator = TerminalProgressIndicator(stream, bar_width=10, clock=lambda: now[0], render_interval=0)

    with indicator.download("Downloading Scryfall default_cards", "default-cards.jsonl.gz") as on_progress:
        now[0] = 2.0
        on_progress(1024 * 1024, 4 * 1024 * 1024)

    output = stream.getvalue()
    assert "\r" in output
    assert "default-cards.jsonl.gz" in output
    assert "[##........]" in output
    assert "1.0 MiB / 4.0 MiB (25%)" in output
    assert "512.0 KiB/s" in output
    assert output.endswith("\n")


def test_terminal_indicator_logs_plain_lines_when_not_a_tty() -> None:
    stream = io.StringIO()
    indicator = TerminalProgressIndicator(stream, clock=lambda: 1.0, render_interval=0)

    indicator.status("Building the local Scryfall card database...")
    indicator.status("Building the local Scryfall card database...")
    with indicator.download("Downloading Scryfall oracle_cards", "oracle.jsonl.gz") as on_progress:
        on_progress(10, 100)
    indicator.idle()

    lines = stream.getvalue().splitlines()
    assert lines[0] == "Building the local Scryfall card database..."
    assert lines[1] == "Downloading Scryfall oracle_cards (oracle.jsonl.gz)..."
    assert lines[2].startswith("Downloading Scryfall oracle_cards (oracle.jsonl.gz): done")
    assert "\r" not in stream.getvalue()
    assert len(lines) == 3
