"""Console entry points for the individual MTG helper scripts."""

from __future__ import annotations

import runpy


def _run(module_name: str) -> None:
    runpy.run_module(module_name, run_name="__main__")


def build_base_deck() -> None:
    """Run the base-deck builder."""
    _run("mtg_scripts.build_base_deck.build_base_deck")


def calculate_to_purchase() -> None:
    """Run the purchase calculator."""
    _run("mtg_scripts.calculate_to_purchase.calculate_to_purchase")


def cardmarket_optimizer() -> None:
    """Run the Cardmarket offer optimizer."""
    _run("mtg_scripts.cardmarket_optimizer.optimizer")


def cardmarket_scraper() -> None:
    """Run the Cardmarket scraper."""
    _run("mtg_scripts.cardmarket_optimizer.scraper")


def shopping_wizard_optimizer() -> None:
    """Run the Cardmarket shopping wizard optimizer."""
    _run("mtg_scripts.cardmarket_optimizer.shopping_wizard_optimizer")


def gen_dummy_test_files() -> None:
    """Generate Cardmarket optimizer test data."""
    _run("mtg_scripts.cardmarket_optimizer.gen_dummy_test_files")


def cardtrader_optimizer() -> None:
    """Run the CardTrader optimizer."""
    _run("mtg_scripts.cardtrader_optimizer.cardtrader_optimizer")


def deck_exporter() -> None:
    """Run the deck exporter."""
    _run("mtg_scripts.deck_exporter.deck_exporter")


def forge_auto_battler() -> None:
    """Run the Forge auto battler."""
    _run("mtg_scripts.forge_auto_battler.forge_auto_battler")


def moxfield_to_forge() -> None:
    """Run the Moxfield-to-Forge exporter."""
    _run("mtg_scripts.forge_deck_exporter.moxfield_to_forge")


def mana_base_creator() -> None:
    """Run the mana-base creator."""
    _run("mtg_scripts.mana_base_creator.mana_base_creator")


def count_occurrences() -> None:
    """Run the line-occurrence counter."""
    _run("mtg_scripts.other_scripts.count_occurrences")


def filter_list() -> None:
    """Run the list filter."""
    _run("mtg_scripts.other_scripts.filter_list")


def make_mtg_table() -> None:
    """Generate the MTG reference table document."""
    _run("mtg_scripts.other_scripts.make_mtg_table")


def vanilla() -> None:
    """Run the vanilla-creature search."""
    _run("mtg_scripts.other_scripts.vanilla")


def print_picker() -> None:
    """Run the graphical print picker."""
    _run("mtg_scripts.print_picker.print_picker")
