"""Tests for the package entry-point adapters."""

import ast
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from mtg_scripts import cli

if TYPE_CHECKING:
    from collections.abc import Sequence

ROOT = Path(__file__).resolve().parents[2]
with (ROOT / "pyproject.toml").open("rb") as metadata_file:
    PROJECT = tomllib.load(metadata_file)["project"]
COMMANDS = PROJECT["scripts"] | PROJECT["gui-scripts"]
TREE = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
FEATURES = {
    node.name: next(
        call.args[0].value
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_run"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    )
    for node in TREE.body
    if isinstance(node, ast.FunctionDef) and node.name in COMMANDS
}

SAFETY_PROBE = r"""
import argparse
import builtins
import importlib
import importlib.abc
import os
import sys

import curl_cffi.requests
import docx
import filelock
import PIL.Image
import platformdirs
import requests
import tkinter

module_name, action = sys.argv[1:]

def forbidden(*args, **kwargs):
    raise AssertionError("unexpected side effect")

class MissingAutomation(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"selenium", "pyautogui", "pywinauto", "tesserocr", "wakepy", "pyedhrec"}:
            raise ModuleNotFoundError("automation dependency intentionally unavailable: " + fullname)
        return None

def audit(event, arguments):
    if event == "open":
        _, mode, flags = arguments
        if (mode and any(flag in mode for flag in "wax+")) or (
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        ):
            forbidden()
    if event in {"os.mkdir", "os.remove", "os.rename", "os.rmdir", "subprocess.Popen", "os.system", "os.startfile",
                 "socket.connect", "socket.bind", "socket.getaddrinfo", "ctypes.dlopen"}:
        forbidden()

sys.meta_path.insert(0, MissingAutomation())
sys.addaudithook(audit)
requests.sessions.Session.request = forbidden
curl_cffi.requests.get = forbidden
curl_cffi.requests.Session.request = forbidden
tkinter.Tk.__init__ = forbidden
tkinter.Toplevel.__init__ = forbidden
builtins.input = forbidden
if action == "import":
    argparse.ArgumentParser.parse_args = forbidden
    argparse.ArgumentParser.parse_known_args = forbidden
module = importlib.import_module(module_name)
assert callable(module.main)
if action == "missing":
    arguments = {
        "mtg_scripts.build_base_deck.build_base_deck": ["--commander-names", "Test Commander"],
        "mtg_scripts.cardmarket_optimizer.scraper": ["--username", "test-user", "--password", "test-placeholder"],
        "mtg_scripts.cardmarket_optimizer.shopping_wizard_optimizer": [
            "--wants-list-id", "1", "--username", "test-user", "--password", "test-placeholder",
        ],
        "mtg_scripts.cardtrader_optimizer.cardtrader_optimizer": ["--card-list", "fixture.txt"],
        "mtg_scripts.forge_auto_battler.forge_auto_battler": ["one", "two", "three", "four"],
    }
    assert module.main(arguments[module_name]) == 1
elif action != "import":
    try:
        module.main(["--help"] if action == "help" else ["--phase2-invalid-option"])
    except SystemExit as error:
        assert error.code == (0 if action == "help" else 2), error.code
    else:
        raise AssertionError("parser did not exit")
"""


def test_cli_exports_all_entry_points() -> None:
    with (Path(__file__).resolve().parents[2] / "pyproject.toml").open("rb") as metadata_file:
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


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("argv", [None, ["fixture.txt"]])
def test_cli_forwards_arguments_and_status(
    monkeypatch: pytest.MonkeyPatch, command: str, argv: Sequence[str] | None
) -> None:
    imported: list[str] = []
    arguments: list[Sequence[str] | None] = []

    def fake_main(options: Sequence[str] | None) -> int:
        arguments.append(options)
        return 7

    def fake_import(name: str) -> SimpleNamespace:
        imported.append(name)
        return SimpleNamespace(main=fake_main)

    monkeypatch.setattr(cli, "_import_module", fake_import)
    assert getattr(cli, command)(argv) == 7
    assert imported == [FEATURES[command]]
    assert arguments == [argv]


@pytest.mark.parametrize(
    ("module_name", "action"),
    [
        *[
            (module, action)
            for module in [*FEATURES.values(), "mtg_scripts.cardtrader_optimizer.diff"]
            for action in ("import", "help", "invalid")
        ],
        *[
            (FEATURES[command], "missing")
            for command in (
                "build_base_deck",
                "cardmarket_scraper",
                "shopping_wizard_optimizer",
                "cardtrader_optimizer",
                "forge_auto_battler",
            )
        ],
    ],
)
def test_commands_are_safe_without_automation_dependencies(tmp_path: Path, module_name: str, action: str) -> None:
    environment = os.environ | {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT / "src"),
        "MTG_SCRIPTS_CACHE_DIR": str(tmp_path / "cache"),
    }
    result = subprocess.run(
        [sys.executable, "-B", "-c", SAFETY_PROBE, module_name, action],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not list(tmp_path.iterdir())
