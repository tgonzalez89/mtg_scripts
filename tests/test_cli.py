"""Tests for the package entry-point adapters."""

from mtg_scripts import cli


def test_cli_exports_all_entry_points() -> None:
    expected = {
        "build_base_deck",
        "calculate_to_purchase",
        "cardmarket_optimizer",
        "cardmarket_scraper",
        "shopping_wizard_optimizer",
        "gen_dummy_test_files",
        "cardtrader_optimizer",
        "deck_exporter",
        "forge_auto_battler",
        "moxfield_to_forge",
        "mana_base_creator",
        "count_occurrences",
        "filter_list",
        "make_mtg_table",
        "vanilla",
        "print_picker",
    }

    assert expected <= set(vars(cli))
