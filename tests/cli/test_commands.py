import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from mtg_scripts import commands

if TYPE_CHECKING:
    import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_lists_every_declared_command_with_its_summary(capsys: pytest.CaptureFixture[str]) -> None:
    with (ROOT / "pyproject.toml").open("rb") as metadata_file:
        project = tomllib.load(metadata_file)["project"]

    listed = dict(commands.list_commands())

    assert set(listed) == set(project["scripts"]) | {f"{name} (GUI)" for name in project["gui-scripts"]}
    assert all(listed.values())
    assert commands.main([]) == 0
    output = capsys.readouterr().out
    assert "mana_base_recipe" in output
    assert "print_picker (GUI)" in output
