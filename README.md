# MTG Scripts

A collection of command-line and graphical tools for Magic: The Gathering deck building, card lookup, purchasing, and automation.

## Setup

[Install uv](https://docs.astral.sh/uv/#installation), then run:

```bash
uv sync
```

uv creates the project environment and downloads a compatible managed Python version when needed.

To install the repository's Git hooks:

```bash
uv run pre-commit install --install-hooks
```

## Available commands

The project scripts are declared in [`pyproject.toml`](pyproject.toml). The available commands are listed here:

**Command-line tools:** `build_base_deck`, `calculate_to_purchase`, `cardmarket_optimizer`, `cardmarket_scraper`, `shopping_wizard_optimizer`, `gen_dummy_test_files`, `cardtrader_optimizer`, `deck_exporter`, `forge_auto_battler`, `mana_base_creator`, `mana_base_recipe`, `count_occurrences`, `filter_list`, `make_mtg_table`, and `vanilla`.

**Graphical application:** `print_picker`.

Run a command with `uv run <command> [args...]`; add `--help` to see its options. Launch Print Picker with `uv run print_picker`.

## Forge OCR

Forge automation requires a local Forge installation and Tesseract OCR data. Download the data from [tesseract-ocr/tessdata](https://github.com/tesseract-ocr/tessdata). Set `MTG_SCRIPTS_TESSDATA_DIR` to its directory or pass `--tessdata-dir PATH` to the Forge command.

## Tests

Run the test suite with:

```bash
uv run pytest
```

For offline tests that do not require network access, browsers, or a graphical desktop:

```bash
uv run pytest -m "not network and not browser and not gui and not memory"
```
