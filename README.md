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

Run `uv run mtg_scripts` to list every installed command with a one-line description.

Run a command with `uv run <command> [args...]`. Add `--help` to see its options.

## Forge OCR

Forge automation requires a local Forge installation and Tesseract OCR data. Download the data from [tesseract-ocr/tessdata](https://github.com/tesseract-ocr/tessdata). Set `MTG_SCRIPTS_TESSDATA_DIR` to its directory or pass `--tessdata-dir <path>` to the Forge automation command.

## Tests

Run the test suite with:

```bash
uv run pytest
```

For offline tests that do not require network access, browsers, or a graphical desktop:

```bash
uv run pytest -m "not network and not browser and not gui and not memory"
```
