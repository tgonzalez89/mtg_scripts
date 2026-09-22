# MTG Scripts

A collection of command-line and graphical tools for Magic: The Gathering deck building, collection management, card purchasing, and automation.

## Setup

Install [uv](https://docs.astral.sh/uv/#installation) and run `uv sync` to create the project environment. The Forge auto battler also requires a local Forge installation and Tesseract OCR data. The `tesserocr` package can require a platform-specific wheel.

After cloning (or re-cloning) the repository, install the git hooks so `pre-commit` checks run automatically:

```bash
uv run pre-commit install --install-hooks
```

Git hooks live under `.git/hooks`, which is not tracked by git, so this step must be repeated for every new clone.

### Optional Dependencies

Some scripts require dependencies that are not installed by default. To install all dependencies, run:

```bash
uv sync --all-extras
```

### tesserocr on Windows

`tesserocr` has no official Windows wheel on PyPI. Before running `uv sync --all-extras` you must provide the wheel manually:

1. **Install Tesseract-OCR** on your machine.
   Follow the instructions on the [tesserocr PyPI page](https://pypi.org/project/tesserocr/).

2. **Download the matching wheel** for your Python version and architecture from:
   [https://github.com/simonflueckiger/tesserocr-windows_build/releases](https://github.com/simonflueckiger/tesserocr-windows_build/releases)

   Pick the file that matches your setup, e.g.:
   `tesserocr-2.11.0-cp314-cp314-win_amd64.whl` for Python 3.14 on 64-bit Windows.

3. **Place the wheel** in the `wheels/` directory at the repository root:
   ```
   mtg_scripts/
   └── wheels/
       └── tesserocr-2.11.0-cp314-cp314-win_amd64.whl
   ```

4. **Uncomment** the [tool.uv] and [tool.uv.sources] sections in the pyproject.toml

5. **Run `uv sync --all-extras`** - `uv` will pick up the wheel automatically from that directory.

> **Note:** The `wheels/` directory is git-ignored for `.whl` files, so wheels are never committed to the repository. The platform's wheel must be manually added locally.

## CLI entries

- `build_base_deck`
- `calculate_to_purchase`
- `cardmarket_optimizer`
- `cardmarket_scraper`
- `shopping_wizard_optimizer`
- `gen_dummy_test_files`
- `cardtrader_optimizer`
- `deck_exporter`
- `forge_auto_battler`
- `moxfield_to_forge`
- `mana_base_creator`
- `count_occurrences`
- `filter_list`
- `make_mtg_table`
- `vanilla`

Each entry point provides its own `--help` output where command-line options apply.

## GUI entry

- `print_picker`

## Project layout

Python packages live under `src/mtg_scripts`, with one directory per tool family. Tests live under `tests`; repository tooling is configured in `pyproject.toml` and `.pre-commit-config.yaml`.

## License

See [LICENSE](LICENSE).
