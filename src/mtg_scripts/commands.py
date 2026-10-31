"""List every command installed by the mtg-scripts package."""

from __future__ import annotations

import argparse
import inspect
import sys
from importlib.metadata import PackageNotFoundError, distribution
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

DISTRIBUTION = "mtg-scripts"
_GROUPS = {"console_scripts": "", "gui_scripts": " (GUI)"}


def list_commands() -> list[tuple[str, str]]:
    """Return `(command, summary)` pairs read from the installed entry points."""
    commands: list[tuple[str, str]] = []
    for entry_point in distribution(DISTRIBUTION).entry_points:
        if entry_point.group not in _GROUPS:
            continue
        summary = (inspect.getdoc(entry_point.load()) or "").partition("\n")[0]
        commands.append((entry_point.name + _GROUPS[entry_point.group], summary))
    return sorted(commands)


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description="List the commands provided by mtg-scripts.").parse_args(argv)
    try:
        commands = list_commands()
    except PackageNotFoundError:
        print(f"The {DISTRIBUTION} package is not installed; run 'uv sync' first.", file=sys.stderr)
        return 1
    width = max(len(name) for name, _ in commands)
    print("Available mtg-scripts commands:")
    for name, summary in commands:
        print(f"  {name.ljust(width)}  {summary}".rstrip())
    print("\nRun '<command> --help' for the options of a command.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
