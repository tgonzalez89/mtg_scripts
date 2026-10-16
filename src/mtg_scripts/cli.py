"""Console entry points for the individual MTG helper scripts."""

from __future__ import annotations

from importlib import import_module as _import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def _run(module_name: str, argv: Sequence[str] | None = None) -> int:
    entry_point = getattr(_import_module(module_name), "main", None)
    if not callable(entry_point):
        message = f"Command module {module_name!r} has no callable main entry point."
        raise TypeError(message)
    status = entry_point(argv)
    if not isinstance(status, int):
        message = f"Command module {module_name!r} returned a non-integer status."
        raise TypeError(message)
    return status


def build_base_deck(argv: Sequence[str] | None = None) -> int:
    """Run the base-deck builder."""
    return _run("mtg_scripts.build_base_deck.build_base_deck", argv)


def calculate_to_purchase(argv: Sequence[str] | None = None) -> int:
    """Run the purchase calculator."""
    return _run("mtg_scripts.calculate_to_purchase.calculate_to_purchase", argv)


def cardmarket_optimizer(argv: Sequence[str] | None = None) -> int:
    """Run the Cardmarket offer optimizer."""
    return _run("mtg_scripts.cardmarket_optimizer.optimizer", argv)


def cardmarket_scraper(argv: Sequence[str] | None = None) -> int:
    """Run the Cardmarket scraper."""
    return _run("mtg_scripts.cardmarket_optimizer.scraper", argv)


def shopping_wizard_optimizer(argv: Sequence[str] | None = None) -> int:
    """Run the Cardmarket shopping wizard optimizer."""
    return _run("mtg_scripts.cardmarket_optimizer.shopping_wizard_optimizer", argv)


def gen_dummy_test_files(argv: Sequence[str] | None = None) -> int:
    """Generate Cardmarket optimizer test data."""
    return _run("mtg_scripts.cardmarket_optimizer.gen_dummy_test_files", argv)


def cardtrader_optimizer(argv: Sequence[str] | None = None) -> int:
    """Run the CardTrader optimizer."""
    return _run("mtg_scripts.cardtrader_optimizer.cardtrader_optimizer", argv)


def deck_exporter(argv: Sequence[str] | None = None) -> int:
    """Run the deck exporter."""
    return _run("mtg_scripts.deck_exporter.deck_exporter", argv)


def forge_auto_battler(argv: Sequence[str] | None = None) -> int:
    """Run the Forge auto battler."""
    return _run("mtg_scripts.forge_auto_battler.forge_auto_battler", argv)


def mana_base_creator(argv: Sequence[str] | None = None) -> int:
    """Run the mana-base creator."""
    return _run("mtg_scripts.mana_base_creator.mana_base_creator", argv)


def mana_base_recipe(argv: Sequence[str] | None = None) -> int:
    """Run the mana-base recipe launcher."""
    return _run("mtg_scripts.mana_base_creator.mana_base_recipe", argv)


def count_occurrences(argv: Sequence[str] | None = None) -> int:
    """Run the line-occurrence counter."""
    return _run("mtg_scripts.other_scripts.count_occurrences", argv)


def filter_list(argv: Sequence[str] | None = None) -> int:
    """Run the list filter."""
    return _run("mtg_scripts.other_scripts.filter_list", argv)


def make_mtg_table(argv: Sequence[str] | None = None) -> int:
    """Generate the MTG reference table document."""
    return _run("mtg_scripts.other_scripts.make_mtg_table", argv)


def vanilla(argv: Sequence[str] | None = None) -> int:
    """Run the vanilla-creature search."""
    return _run("mtg_scripts.other_scripts.vanilla", argv)


def print_picker(argv: Sequence[str] | None = None) -> int:
    """Run the graphical print picker."""
    return _run("mtg_scripts.print_picker.print_picker", argv)
