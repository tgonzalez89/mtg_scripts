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

Install Tesseract-OCR and its required data following the instructions on the
[tesserocr PyPI page](https://pypi.org/project/tesserocr/), then install the Forge extra:

```bash
uv sync --extra forge
```

On standard CPython on Windows, uv automatically downloads and caches the `tesserocr` wheel from the [Windows wheel releases](https://github.com/simonflueckiger/tesserocr-windows_build/releases).
No manual download or configuration edits are needed. `uv sync --all-extras` uses the same source.

On Linux and other nonmatching environments, uv resolves `tesserocr` from PyPI,
which may require a source build and system Tesseract development libraries.
The configured Windows wheel does not cover all Python versions, architectures,
or free-threaded Python builds; those require a compatible wheel or source build.
To bypass the configured source explicitly, use `uv sync --extra forge --no-sources`.

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
- `mana_base_creator`
- `mana_base_recipe`
- `count_occurrences`
- `filter_list`
- `make_mtg_table`
- `vanilla`

Each entry point provides its own `--help` output where command-line options apply.

Use `deck_exporter` for Moxfield-to-Forge exports; `moxfield_to_forge` is not a declared command.

### Callable Commands

Every command exposes `main(argv=None) -> int` in its feature module. The functions in `mtg_scripts.cli` lazily import only the selected command and forward its arguments and status. Importing an executable module does not run its workflow or parse process arguments.

Successful workflows return `0`; expected file, service, runtime-dependency, or automation failures return `1` with a diagnostic. Argparse retains `SystemExit(0)` for help and `SystemExit(2)` for invalid arguments. Direct module execution exits with the returned status. All command help paths work without opening windows, starting browsers, or requiring Forge/OCR/automation dependencies.

Mana-base options use kebab-case, such as `--total-lands`, `--price-source`, and `--enable-groups`; underscore spellings are rejected. Recipe positional arguments and explicit extra-option overrides are retained, and the recipe returns the creator's status.

The `vanilla` command now defaults to `vanilla_creatures.txt` in the working directory rather than beside the installed script; use `--output` for a different location. CardTrader accepts `--output-dir` for its three JSON outputs and still defaults to the working directory. Forge/XMage deck destinations and file formats are unchanged.

## GUI entry

- `print_picker`

## Project layout

Python packages live under `src/mtg_scripts`, with one directory per tool family. Cross-feature primitives live in `common`, provider integration in `services`, and site-specific models/helpers remain in their feature directories. Tests mirror these owners, including `tests/common`, `tests/services`, and feature directories. Repository tooling is configured in `pyproject.toml` and `.pre-commit-config.yaml`.

### Shared Utilities

`common.card_lists` owns plain quantity/name parsing and aggregation. It retains existing whitespace, lowercase-key, slash-separator, and malformed-line behavior; display names are available separately. Purchased-order paste parsing, collection CSV, and Scryfall/RiftCodex printing-hint syntax remain distinct feature adapters.

`common.json_io` owns repeated JSON reading/writing. Writes use a temporary file beside the destination and replace it only after serialization succeeds, with cleanup on failure. Callers still select indentation, sorting, newline behavior, and destinations; missing parent directories are not created automatically. This is file persistence, not a shared cache or locking system.

`services.moxfield` centralizes deck IDs, wire payload types, validation, fetching, response cleanup, and `MoxfieldError`. Fetching uses an injected transport: the purchase calculator retains `requests`, while the exporter retains `curl_cffi`, Chrome impersonation, and its existing headers. Purchase section accounting and Forge/XMage formatting remain independent. Deck responses are not persistently cached; existing command debug dumps retain their separate formatting policies.

`cardmarket_optimizer.models` shares core offer fields while keeping scraper metadata and selection fields distinct. The optimizer's explicit copy adapter preserves metadata during mutable selection. Browser selectors, alert handling, and number parsing stay Cardmarket-local.

### Shared Cache and HTTP

Shared backend caches default to `platformdirs`' per-user `mtg-scripts` cache root. Override it with `MTG_SCRIPTS_CACHE_DIR`; the Print Picker `--cache-dir PATH` option takes precedence over the environment. Backend constructors also accept an explicit cache root. Resolving a path alone does not create directories. Data is separated by provider and category, for example `scryfall/{json,images,bulk,metadata}` and `riftcodex/{json,images}`. `platformdirs` selects OS-specific cache locations; `filelock` coordinates access across processes. Both are direct runtime dependencies.

JSON entries use versioned provider/fetch-time/freshness envelopes; image/bulk bytes and JSON files publish by atomic replacement. Per-key file locks coordinate processes, request coalescing avoids duplicate in-process fetches, and cache clearing advances a namespace epoch before reclaiming old entries. The HTTP client serializes access to its Session, closes responses, retries idempotent GETs with bounded backoff/jitter and `Retry-After`, and does not retry POSTs. Scryfall API requests have a cross-process 100 ms minimum interval; image and bulk CDN transfers use their own download policy.

Existing Print Picker `.cache` JSON and images are imported lazily without deleting the originals. Legacy JSON is considered stale and refreshed; URL-addressed images remain reusable. A schema-valid Scryfall v8 SQLite database is copied to the new cache root only after integrity checks. Older v5/v6/v7 files are retained but are not reused; the compact v8 schema requires a fresh build. Bulk metadata is fresh for 24 hours, refreshed builds publish a separate database generation, and failed refreshes fall back with a warning to the newest valid local generation. “Clear request cache” and “Clear image cache” do not delete the bulk database. Old database generations are retained; automatic database garbage collection is deferred. The first uncached Scryfall run may download substantial bulk data.

Print Picker, mana-base creator, and vanilla use the shared Scryfall service. Mana-base resolves simple Oracle Tag
groups and exact names from the local SQLite store, then filters paper/Commander legality and prices locally. It uses
API search for custom Scryfall query syntax and falls back to it when local tag/name data is unavailable. Local price
selection is limited to printings indexed in the current bulk database; it is not a guarantee of the cheapest printing
across every Scryfall printing. Mana-base and vanilla API fallbacks complete pagination. Expired search snapshots are
used only with `--allow-stale-data` and emit the service warning.

### Scryfall Service

`services.scryfall.ScryfallService` owns a provider-neutral v8 SQLite store, bulk manager, hierarchical Oracle Tag lookup, and cached API search. The store extracts only fields consumed by the scripts: printing identity/display/image fields, Oracle text, color identity, Commander legality, supported prices, type, mana cost/value, power, and toughness. Full card JSON, unused URLs/metadata, other format legalities, and unused tag weights are not stored. Both API searches and database lookups return the same typed records. Bulk JSONL is streamed and only queried rows are loaded. Oracle tags from the optional `oracle_tags` bulk entry are indexed by stable tag ID, slug, parent/child edges, and oracle ID. `cards_for_tag("otag:cycle-fetchland")` traverses descendants and returns printings for tagged oracle cards. If tag hierarchy or printing coverage is incomplete, the service reports the local lookup as unavailable so callers can fall back safely. Adding persisted fields requires a new schema version and rebuild.

The service exposes batch name lookup, print-ID/oracle-ID lookup, tag lookup, and full Scryfall search. Arbitrary query
syntax remains API-backed; the service does not approximate the Scryfall query language locally. Mana-base uses tag
membership/name lookup for simple local candidate discovery, then applies its relevant filters and ordering to stored
fields. The store contains the bulk printings currently indexed, so local prices may not represent a cheaper printing
outside that data. API search caches complete paginated results and validates each `next_page` URL. Negative results
are cached for one hour and other search snapshots for 24 hours. Offline search requires the exact query to be cached.
Stale results produce a warning and require explicit permission, including for price-sensitive callers.

The Print Picker adapter delegates storage to this service but retains its name parsing and printing preferences. The
application owns one service and shares it across backend instances; shutdown waits for active workers before closing
the service. Mana-base uses local tag/name discovery for the standard groups and cached API searches for custom query
groups or local misses; vanilla continues to use cached full API search.

## Testing

Run the offline suite without opening windows, starting browsers, or downloading card data:

```bash
uv run pytest -m "not network and not browser and not gui and not memory"
```

Use `uv run pytest tests/print_picker` or another test directory for focused checks. The memory integration test remains opt-in through `RUN_PRINT_PICKER_MEMORY_TESTS=1`; it needs Windows, a graphical desktop, and network access.

See [tests/README.md](tests/README.md) for marker definitions, baseline results, fixture contracts, command safety tests, shared cache/HTTP and Scryfall service coverage, Phase 6 consumer fixtures, Phase 7 pure helper coverage, and the historical pre-refactor compatibility inventory. Phase 8 integration and packaging gates remain.

## License

See [LICENSE](LICENSE).
