"""Tests for the package entry-point adapters."""

import tomllib
from pathlib import Path

from mtg_scripts import cli


def test_cli_exports_all_entry_points() -> None:
    with (Path(__file__).resolve().parents[1] / "pyproject.toml").open("rb") as metadata_file:
        project = tomllib.load(metadata_file)["project"]
    entry_points = project["scripts"] | project["gui-scripts"]
    expected = set()
    for target in entry_points.values():
        module_name, attribute = target.split(":")
        assert module_name == cli.__name__
        assert callable(getattr(cli, attribute))
        expected.add(attribute)

    actual = {name for name, value in vars(cli).items() if not name.startswith("_") and callable(value)}
    assert actual == expected
