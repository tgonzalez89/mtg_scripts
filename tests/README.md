# Test Ownership and Refactoring Baseline

Phase 1 baseline recorded on 2026-10-15 using the repository's uv environment on Windows.
The Phase 1 snapshot below records the original contracts. Phase 2 through Phase 7 changes are listed separately before that historical inventory.

## Phase 7 Feature Decomposition

- `tests/build_base_deck/test_build_base_deck.py` stubs the EDHREC adapter and checks exact main/considering output after regular/budget selection and price filtering.
- The purchase CLI's existing golden test continues to cover variant-deck maxima, independent-deck sums, allocated inventory, and considering output after moving parsing/calculation into feature-local modules.
- Cardmarket optimizer fixtures retain selected offers, totals, tie-breaking, and generated database compatibility. Shopping Wizard and CardTrader lifecycle tests use fake drivers and verify `quit()` after failures; no login, cart mutation, or real browser is run.
- CardTrader pure tests cover language-threshold parsing, text chunking, accumulated price thresholds, and per-card cent conversion.
- Forge tests cover typed CLI options, tessdata environment/argument selection, directory validation, session-owned window references, and OCR normalization/binarization. Forge itself is not launched and OCR is not run against a real screen.
- Mana-base tests retain disabled-group, query, price-order, and recipe override behavior while candidate acquisition, filters, allocation, and typed recipe configuration are separated.
- Print Picker export helpers are tested without Tk for copy/face filename planning, slot aggregation, unresolved-card omission, and unique-image encoding via the existing download tests.
- Deck Exporter keeps its existing named section extraction and Forge/XMage renderers; the small standalone tools remain functions rather than gaining unnecessary modules.

```bash
uv run pytest tests/build_base_deck tests/calculate_to_purchase tests/cardmarket_optimizer tests/cardtrader_optimizer tests/forge_auto_battler tests/mana_base_creator tests/other_scripts/test_vanilla.py tests/print_picker/test_export_helpers.py
```

## Phase 8 Integration Gates

The Windows CI workflow runs the offline marked suite, full Ruff lint/format, strict `ty`, `uv lock --check`, all
pre-commit hooks, `uv build`, and an isolated wheel install followed by `--help` smoke tests for every metadata-defined
console/GUI command. It installs no Forge extra and does not require the local Tesseract wheel.

Run the repository hooks locally with:

```bash
uv run pre-commit run --all-files
```

## Phase 6 Scryfall Consumers

- Mana-base tests verify local Oracle Tag/name resolution avoids API search when indexed data is available, filters out non-paper/non-Commander cards, selects the lowest configured local price per oracle, and falls back to cached API search for custom groups or missing names/tags. API fallback still preserves exact query/order behavior. `--allow-stale-data` remains opt-in for that path.
- Vanilla tests verify arbitrary query forwarding, `cmc` ascending parameters, typed ranking fields, zero mana value, `cmc` extraction, unknown stats, tie/order behavior, and formatted output. The service completes pagination; queries previously truncated can now return additional cards.
- A cross-consumer service integration test runs both mana-base and vanilla through the same search namespace, then creates a second service against that cache root and confirms both results are served without HTTP requests.
- Print Picker tests verify that closing a backend leaves an injected service open. The app shares one service across backend instances and waits for workers before closing resources. No live Tk lifecycle or network test is run by this offline suite.
- Standard mana-base Oracle Tag groups use `cards_for_tag()` and local legality/paper/price filters; unsupported custom Scryfall queries retain the complete API path. Local cheapest-price choice is bounded by the printings present in the current bulk database and does not claim global cheapest-printing equivalence.

```bash
uv run pytest tests/mana_base_creator tests/other_scripts/test_vanilla.py tests/print_picker/test_scryfall_backend.py tests/services/scryfall
```

## Phase 5 Scryfall Service

- `tests/services/scryfall/test_store.py` builds real SQLite v8 files from in-memory cards and tiny gzipped JSONL inputs. It verifies explicit consumed fields (including all supported prices), absence of raw payloads/unused tag weights, API/database record parity, name/printing lookup, schema validation, optional tags, recursive parent-to-leaf tag lookup, oracle-ID-to-all-printings joins, and tag provenance/build metadata.
- `tests/services/scryfall/test_service.py` stubs HTTP responses and covers metadata with/without `oracle_tags`, offline database use/miss, complete multi-page search caching, URL-origin validation, pagination-loop/malformed-page rejection, one-hour 404 caching, and explicit stale/offline behavior. No live Scryfall request or full bulk download is made.
- Scryfall search tests distinguish API errors from a genuine 404/no-results response; incomplete pagination never becomes a cached result. Stale price data is warned about and requires an explicit stale-data policy.
- Legacy v5/v6/v7 databases are not compatible with the compact v8 schema and are retained but not migrated. Tests use tiny v8 databases. Oracle tags are optional metadata; older metadata still builds a valid database with `has_oracle_tags=False`.
- Print Picker selection/export behavior remains covered by `tests/print_picker/test_scryfall_backend.py`; the backend now owns conversion from neutral service records to its UI-specific printing model, while database fixtures use `services.scryfall.store` directly.

```bash
uv run pytest tests/services/scryfall tests/print_picker/test_scryfall_backend.py tests/print_picker/test_cache_integration.py
```

## Phase 4 Cache and HTTP Contracts

- `CachePaths.resolve(explicit, environ=...)` precedence is explicit path, `MTG_SCRIPTS_CACHE_DIR`, then `platformdirs.user_cache_path("mtg-scripts")`. Path resolution does not create a directory. Provider/category components reject separators and traversal. Print Picker forwards `--cache-dir`; all backend constructors accept an explicit path.
- JSON and byte caches use canonical request keys, versioned JSON envelopes, timestamps, freshness policy, namespace/provider identity, atomic temporary-file replacement, per-key `filelock` locks, and in-process coalescing. Cache clears advance an epoch, safely reclaim only prior-generation entries, and cannot republish an in-flight old generation. Cache directory creation occurs only on use/clear.
- Process tests launch independent Python processes: two JSON-cache clients fetch one key and exactly one loader runs; two Scryfall clients over tiny local gzip fixtures publish one validated database and make zero HTTP requests.
- HTTP tests cover bounded GET retries, Retry-After seconds/date, maximum delay, jitter injection, no POST retry, response closure, session ownership, JSON cache key separation/expiry, byte responses, persistent rate limiting, streamed chunks, interrupted stream retry, progress, and preservation of an existing file when a download fails.
- The Scryfall API limiter coordinates through the Scryfall metadata namespace and waits at least 100 ms between processes. Print Picker image and bulk CDN transfers explicitly bypass this API limiter. RiftCodex uses the generic bounded retry behavior without Scryfall pacing.
- Existing package-local JSON/image cache files are considered only when no explicit constructor cache root was given. Matching raw JSON is imported with its original filesystem timestamp and a 24-hour stale policy, then re-fetched; image bytes are copied lazily by the old URL digest and the originals remain. Corrupt image data is discarded and fetched again. No arbitrary working directories are scanned.
- Tests cover cache envelope corruption/unsupported versions, invalidation epoch recovery, interrupted atomic writes, and a clear racing with a cache fill. Clear reclaims only old-epoch entries; a concurrently written current-epoch entry remains valid.
- Only current-schema, integrity-checked v8 SQLite generations migrate. Earlier v5/v6/v7 databases remain untouched and are not reused. Bulk metadata uses the 24-hour shared envelope. A build lock serializes metadata/build work across processes; bulk downloads stream into temporary files. A corrupt current generation is never overwritten: a new uniquely named generation is built. Old DB generations remain available; consumed compressed inputs are removed only after a successful DB build.
- A metadata/network/build refresh failure falls back to the newest valid local generation with a warning. `clear_json_cache()` and `clear_image_cache()` target separate provider namespaces and do not remove bulk DBs. `ScryfallBackend.refresh_database()` is the explicit refresh operation; current DB handles stay open until backend shutdown. The GUI does not yet expose a refresh button.
- Phase 4 initially wired shared storage into Print Picker/RiftCodex. Phase 6 migrates mana-base and vanilla to the search service while keeping their query/ranking policies in their owning features.

```bash
uv run pytest tests/common tests/print_picker/test_cache_integration.py tests/print_picker/test_cache_cli.py
```

The bulk build test uses tiny local gzip files; no Scryfall, RiftCodex, or image network is required.

## Phase 3 Shared-Code Contracts

- `tests/common/test_card_lists.py` characterizes the old parser before consumer migration: blanks, repeated quantities, whitespace, apostrophes/Unicode, split separators, slash-containing names, zero quantities, malformed prefixes, and single-pass iterables. Matching keys deliberately retain `.lower()` rather than introducing `casefold()` collisions. Numeric/malformed prefixes and comment-looking lines retain their old interpretation; richer printing formats are not parsed here.
- `tests/common/test_json_io.py` checks exact JSON bytes for caller indentation/sorting/newline policies, round trips, malformed reads, serialization/replacement failures, temporary cleanup, and preservation of the old destination. Parent directories are not created implicitly. Atomic publication does not add shared-cache policy or multi-process locking.
- `tests/services/test_moxfield.py` checks ID normalization, optional wire fields, preservation of unknown payload fields, malformed/empty responses, explicit transport/domain errors, response closure, and repeated uncached requests. Consumer integration stubs both `requests.get` and `curl_cffi.requests.get`, verifying timeout/header/impersonation settings and independent section policies.
- Purchase integration retains companion-card aggregation and grouped/max-copy inventory accounting. Export integration retains printing metadata and formatting, tolerates its optional sections, and returns `None` on provider failure. The purchase adapter propagates `MoxfieldError` to its status-1 workflow boundary; transport causes remain chained. Malformed provider JSON now follows that same explicit failure path instead of being mistaken for an empty result.
- Debug-file tests retain purchase dumps' sorted keys and exporter dumps' original insertion order. Provider services never persist deck responses; command-owned debug artifacts remain separate.
- Cardmarket fixtures verify scraper metadata survives the selected-offer adapter without source mutation, and generated five-field offers still feed the optimizer with unchanged output quantities/shipping totals. Schema definitions now live in the feature-local `models.py`; they are not forced onto CardTrader or other markets.
- Existing CLI subprocess safety contracts remain required. All new tests are offline, use temporary files, and do not open a browser or use a real account.

```bash
uv run pytest tests/common tests/services tests/cardmarket_optimizer tests/calculate_to_purchase
```

No command names, flags, file formats, algorithm heuristics, Moxfield transport profiles, or Scryfall behavior change in Phase 3.

## Phase 2 Entry-Point Contracts

- All 16 metadata-defined commands have `main(argv=None) -> int` and thin `SystemExit(main())` module guards. CLI wrappers lazily import the selected feature and propagate arguments/status; `runpy` dispatch is removed.
- Success returns 0 and expected workflow failures return 1. Help and invalid arguments retain argparse status 0 and 2. Programmer errors are not blanket-caught. Recipe overrides retain their precedence and its main returns the creator status.
- Module imports do not parse arguments, read user inputs, create caches/windows/browsers, or enter keep-awake contexts. Browser dependencies load after validation. Forge's launcher checks Windows and runtime prerequisites before importing its local `runtime.py`; this explicit runtime module is not a safe cross-platform CLI import surface.
- Fresh-interpreter tests cover imports, help, and invalid arguments for all commands plus the standalone CardTrader diff utility. They deny optional automation imports, parser calls during import, requests/curl-cffi calls, window construction, process launches, and audited network/write operations. Ordinary third-party libraries are preloaded before guards; the tests verify application boundaries, not third-party initialization. Missing-runtime workflow tests use placeholder inputs and never real credentials.
- Golden workflow fixtures cover grouped/max-copy purchase requirements, allocated and purchased inventory, considering outputs, optimizer shipping and seller tie-breaking, and repeat invocations without retained workflow state. Mana tests cover canonical flag parsing, rejection of underscore spellings, pure basic-land generation, and recipe overrides/status.
- Kebab-case mana options are the only supported long spellings after Phase 8. Vanilla's default output is CWD-relative; CardTrader adds `--output-dir` for JSON destinations. Forge/XMage destinations and data formats remain unchanged. The non-entry-point diff script has callable comparison/main functions and configurable input paths/thresholds.
- A restored root CLI test is preserved alongside `cli/test_cli.py`. Pytest uses importlib mode so both filenames can coexist without import-name collisions.
- File-scoped Ruff complexity exceptions cover the sequential workflows moved from module scope; deeper decomposition remains Phase 7. Lazy imports are intentional at the documented runtime boundaries. The CLI probe's subprocess lint exception is confined to that test file, which executes a fixed script with repository-owned inputs.

Run the contracts and golden workflow fixtures with:

```bash
uv run pytest tests/cli tests/mana_base_creator tests/cardmarket_optimizer tests/calculate_to_purchase
```

No real browser, Forge, GUI memory lifecycle, or remote service workflow is exercised by these checks.

## Running Tests

```bash
uv run pytest --collect-only -q
uv run pytest
uv run pytest -m "not network and not browser and not gui and not memory"
uv run pytest tests/print_picker
uv run pytest tests/mana_base_creator
uv run pytest tests/other_scripts/test_vanilla.py
uv run pytest tests/cli
```

Pytest discovers tests under this directory. Unknown marker names fail because `--strict-markers` is enabled.
Markers describe requirements; a marker by itself does not skip a test or install its prerequisites.

| Marker | Requirement |
| --- | --- |
| `network` | Real external API or image downloads; exempts the test from the default network guard. |
| `browser` | Real browser session; keep out of unattended unit runs. |
| `gui` | Graphical display and Tk event loop. Importing UI helpers without creating a window is not sufficient reason to mark a test. |
| `windows` | Windows-specific integration facilities, not merely a test running on Windows. |
| `memory` | Opt-in resource/memory lifecycle regression checks. |

The existing two-deck memory test carries `network`, `gui`, `windows`, and `memory` markers.
It still skips unless `RUN_PRINT_PICKER_MEMORY_TESTS=1`, and it now explicitly skips on non-Windows systems.
Run it deliberately from PowerShell, on a graphical desktop:

```powershell
$env:RUN_PRINT_PICKER_MEMORY_TESTS = "1"
uv run pytest tests/print_picker/test_print_picker_memory.py -m memory -s
Remove-Item Env:RUN_PRINT_PICKER_MEMORY_TESTS
```

This integration test uses real services and the application's existing default Scryfall cache; first use may download bulk data.
Its RiftCodex backend uses a temporary cache. Shared per-user caches and full integration-cache isolation belong to later phases.

## Ownership and Fixtures

| Owner | Phase 1 test files | Phase 1 collected cases |
| --- | --- | ---: |
| `cli/` | `test_cli.py` | 1 |
| `mana_base_creator/` | `test_mana_base_creator.py` | 1 |
| `print_picker/` | `test_print_picker_download.py` | 2 |
| `print_picker/` | `test_print_picker_loading.py` | 2 |
| `print_picker/` | `test_print_picker_memory.py` | 1 |
| `print_picker/` | `test_riftcodex_backend.py` | 13 |
| `print_picker/` | `test_scryfall_backend.py` | 47 |
| **Total** | **7 files** | **67** |

Counts include parameterized cases, not only test functions. Before and after the moves, all 67 normalized
`filename::test_name[parameters]` identities matched. Files retain their original names to make moves easy to review.
Apart from the documented CLI metadata correction, existing assertions were retained.

Keep payload factories near their tests until multiple suites demonstrably need them. Scryfall tests build a real
temporary SQLite file with `build_from_cards`; they do not download the bulk database. RiftCodex tests stub requests
and set release dates. Image tests write into `tmp_path`; model/loading tests do not create a Tk root. Root
[conftest.py](conftest.py) only owns a global safety boundary, not feature fixtures or GUI initialization.

Unmarked tests fail on `requests.Session.request` and Python socket `connect`/`connect_ex` calls. Stub these operations
or mark an intentional integration test with `network`. This guard covers the current unit-suite HTTP paths; it is
not a sandbox for native clients such as curl-cffi, subprocesses, or code run during module collection. Tests added
for those boundaries must stub their transport explicitly. Phase 2's CLI subprocess probes install their own safety guards.

No empty feature test directories or universal fixture framework are introduced. Shared store tests should move to
`tests/services/scryfall/` only when that production ownership exists.

## Observed Baseline and Phase 1 Corrections

- Before changes, `uv run pytest --collect-only -q` collected 67 cases.
- Before changes, `uv run pytest -q` reported **65 passed, 1 failed, 1 skipped**. The failure was
  `test_cli_exports_all_entry_points`, which expected the undeclared `moxfield_to_forge` adapter. The memory test skipped.
- The corrected CLI test loads both `project.scripts` and `project.gui-scripts` from
  [pyproject.toml](../pyproject.toml) using `tomllib`, checks each target is a callable adapter, and rejects extra public
  adapters. This includes `mana_base_recipe`, omitted by the old handwritten list. It does not execute workflows.
- The first guarded offline run exposed a missing `opp` release-date stub in the RiftCodex fixture:
  `test_a_different_set_does_not_match` reached `/sets/set-id/opp`. Adding the missing fixture value removes an
  accidental live request without changing its assertion or backend code. The original passing suite was therefore
  not completely offline.
- After correction and relocation, `uv run pytest -q` reports **66 passed, 1 skipped**; the explicitly selected offline
  suite reports **66 passed, 1 deselected**. The opt-in GUI/memory workflow was not executed.

## Existing Fixture Contracts

These examples record already-tested behavior rather than introducing new golden-file formats.
See the existing tests for complete fixture payloads and assertions.

| Fixture or input | Current asserted result |
| --- | --- |
| Scryfall `1 Llanowar Elves (m12) 182` | Export text `Llanowar Elves (m12) 182`, excluding the quantity. |
| Same Scryfall printing with `*F*` | Export text retains `*F*`; exported text resolves back to the same printing. |
| Scryfall unknown name | No resolved card; unresolved entries are omitted from exported lists. |
| Two Scryfall backend instances using the same temporary store | Same printing resolves without rebuilding; the store rejects writes. |
| RiftCodex `3 Traveling Merchant (OGN-185)` | Quantity 3, name `Traveling Merchant`, set `ogn`, collector number `185`. |
| RiftCodex API collector number 17 | Printing number is padded to `017`; set mismatch does not match. |
| Three ordinary downloaded copies of one RGBA image | Three files have identical hashes and unchanged pixels; source image is unchanged. |
| Unique downloads across slots, copies, and faces | Five fixture files have distinct hashes; each channel changes by at most one and source pixels remain unchanged. |
| Enabled land group overlaps a disabled group | Disabled `Tapped MDFC` is removed; `Other Candidate` remains at price 1.0; no specific lands remain. |

## Phase 1 Command Compatibility Inventory

The following inventory is source-inspected, not a claim that browser, Forge, network, or file-writing workflows were
executed. Names come from package metadata and target the same-named function in
[cli.py](../src/mtg_scripts/cli.py). At Phase 1, wrappers executed their feature via `runpy.run_module(..., run_name="__main__")`.
Paths below are relative to `src/mtg_scripts/`. Existing feature READMEs are supplementary; parser definitions and
actual writes take precedence when help text differs. Ordinary relative file defaults resolve against the working
directory unless noted. Do not rename arguments, alter defaults, or standardize errors as part of Phase 1.

| Command | Implementation | Inputs and defaults | Outputs and side effects |
| --- | --- | --- | --- |
| `build_base_deck` | `build_base_deck/build_base_deck.py` | Required `--commander-names/-c`; `--themes/-t` defaults to the unthemed selection; synergy/inclusion thresholds 0.15, price threshold 25, vendor `cardkingdom`; `--output-card-list/-o=card_list.txt`. | EDHREC requests; sorted `# MAIN DECK` and `# CONSIDERING` sections in a text file. Parses/runs at import. |
| `calculate_to_purchase` | `calculate_to_purchase/calculate_to_purchase.py` | Required `--want-deck-ids/-w`; `--have-deck-ids/-v=[]`; `--collection-file/-c=collection.csv`; optional purchased/filter files default to `None`, despite help suggesting filenames; `--buy-considering/-b` false. | Moxfield requests; `--to-purchase-file=to_purchase.txt`, `--to-purchase-decks-file=to_purchase_decks.txt`, `--to-purchase-considering-file=to_purchase_considering.txt`; quantity/name lines. Parses/runs at import. |
| `cardmarket_optimizer` | `cardmarket_optimizer/optimizer.py` | `--card-list/-c=card_list.txt`, `--sellers-database/-s=sellers_database.json`, `--offers-database/-o=offers_database.json`. | `--selected-offers/-e=selected_offers.json`; printed item/shipping/total costs and seller count. Reads, mutates offers, and writes at import. |
| `cardmarket_scraper` | `cardmarket_optimizer/scraper.py` | Required `--username/-u`, `--password/-p`; optional browser profile; card list default as above; `--max-editions/-m=25`, `--min-offers-per-edition/-x=25`, `--max-total-offers/-t=500`. | Firefox/account/cart interactions; seller and offer JSON at the `-s/-o` defaults above. Keep-awake context and executable body run at import; no `main`. |
| `shopping_wizard_optimizer` | `cardmarket_optimizer/shopping_wizard_optimizer.py` | Required `--wants-list-id/-i`, `--username/-u`, `--password/-p`; optional `--browser-profile/-b`. | Opens Firefox, logs into Cardmarket, runs shopping wizard and mutates cart contents; printed results. Parses/starts browser at import. |
| `gen_dummy_test_files` | `cardmarket_optimizer/gen_dummy_test_files.py` | Required numeric seller/card counts and shipping/price/amount/offer-count ranges (listed below). | Random seller/offer JSON and buy-list text; output paths use `--sellers-database/-s`, `--offers-database/-o`, `--card-list/-c` defaults above. Guarded body, no `main`. |
| `cardtrader_optimizer` | `cardtrader_optimizer/cardtrader_optimizer.py` | Required `--card-list/-c`; `--expansion-choice/-e=Any`, `--foil-choice/-f=Any`, `--condition/-n=Any`, `--language-price-thresholds/-l` defaults to `Any:0`; optional browser profile. | Firefox wishlist/printing/language interactions; `card_prices_by_lang.json`, `chosen_languages.json`, `final_card_prices.json`, and printed totals. Parses/starts browser at import. |
| `deck_exporter` | `deck_exporter/deck_exporter.py` | Positional `deck_ids+`; `--format/-f=forge` (or `xmage`); `--output-dir/-o=None`; `--no-override/-n` false. | Moxfield requests using curl-cffi impersonation; sanitized deck-name `.dck` files. Forge defaults to `%APPDATA%/Forge/decks/commander`; XMage to `~/Documents/xmage_decks`. Existing files prompt only with `--no-override`. |
| `forge_auto_battler` | `forge_auto_battler/forge_auto_battler.py` | Positional `decks+`, at least four; optional integer `--min-matches=None`. | Focus/click/keyboard/clipboard/screenshot/OCR operations on a real Forge window, keep-awake context, printed win rates. Tesseract data path is machine-specific; debug screenshot writes are enabled. |
| `mana_base_creator` | `mana_base_creator/mana_base_creator.py` | Required `--colors`; `--total_lands=40`, `--min_basics=5`, `--budget=500`, group/specific average price limits 50; `--price_source=usd`; configured group/name defaults; off-color lands false. | Scryfall queries and source-adjacent query cache; progress and alphabetically grouped `quantity name` output with final land count/total price. No output-file argument. |
| `mana_base_recipe` | `mana_base_creator/mana_base_recipe.py` | Six required positionals: `budget`, `theme`, `colors`, `total_lands`, `min_basics`, `price_source`; choices come from local `BUDGETS`/`THEMES`. | Prints generated arguments and calls creator `main`; unknown options are forwarded after recipe arguments. Same acquisition/cache/output effects as creator. |
| `count_occurrences` | `other_scripts/count_occurrences.py` | Positional `files+`. | Reads UTF-8 lines, strips newline only, prints `count<TAB>line`, descending count then alphabetically. No output file. |
| `filter_list` | `other_scripts/filter_list.py` | Positional `input_file`, `remove_file`. | Set difference of newline-stripped UTF-8 lines printed to stdout; duplicates removed, order not guaranteed. |
| `make_mtg_table` | `other_scripts/make_mtg_table.py` | `--output=mtg_table_63x88mm.docx`. | Writes a Word document and prints confirmation. |
| `vanilla` | `other_scripts/vanilla.py` | `--query="type:creature commander:wg (game:paper) is:vanilla"`; optional `--min-mana-value`, `--min-power` default `None`; configurable `--output`. | Live paginated Scryfall search; default output is `vanilla_creatures.txt` beside the implementation, not in CWD; ranked `name | mana value | mana cost | power/toughness | efficiency` lines. |
| `print_picker` (GUI) | `print_picker/print_picker.py` | No command-line parser; input/game/printing selection is interactive. | Tk root, background work, Scryfall/RiftCodex access, clipboard/list export and image downloads; default cache beside the package. Guarded `App().mainloop()`, no `main`. |

### Additional Parser Details

- Base-deck short options: synergy `-s`, inclusion `-i`, price `-p`, vendor `-v`. Vendor choices remain those in its parser.
- Scraper uses `--browser-profile/-b`; shopping wizard and CardTrader use the same spelling. Credentials are currently
  CLI arguments; do not put real values into snapshots, logs, fixtures, or automated workflow runs.
- Generator required options: `--num-sellers`, `--seller-min-shipping-price`, `--seller-max-shipping-price`,
  `--offer-min-price`, `--offer-max-price`, `--offer-min-amount`, `--offer-max-amount`, `--num-cards`,
  `--card-min-offers`, `--card-max-offers`, `--buy-list-min-card-amount`, `--buy-list-max-card-amount`.
- Mana creator accepts only kebab-case long options such as `--max-price-group-average`, `--enable-groups`, and
  `--allow-off-color-lands`; underscore spellings are rejected. Disable lists default empty; enabled query/name lists
  are the literals in its parser. Price choices are `usd`, `eur`, `tix`; recipe uses the same price choices and presets.
- CardTrader foil choices are `Any`, `Yes`, `No`; conditions are `Any`, `Near Mint`, `Slightly Played`,
  `Moderately Played`, `Played`, `Poor`. Language thresholds are cents, first threshold zero, `Any` last.
- `cardtrader_optimizer/diff.py` is not a project entry point and reads `en.json`/`any.json` at import.
  `cardmarket_optimizer/buyer.py` is an unimplemented TODO, not a runnable command.

### Error and Cache Semantics to Characterize Before Changing

- There is no common error/exit policy. Argparse normally exits 0 for help and 2 for parse errors, but imports of
  platform/browser dependencies can fail before parsing. Do not assume every current `--help` is environment-independent.
- Base-deck threshold validation raises `argparse.ArgumentTypeError` after parsing. Purchase CSV parsing raises
  `ValueError` for missing headers/columns, but treats malformed counts as zero; Moxfield HTTP failures propagate.
- Cardmarket optimizer file/JSON errors propagate and its algorithm mutates inputs. Generator invalid ranges raise
  `ValueError`. CardTrader language-threshold validation uses argparse errors, and browser workflows have mixed
  caught/retried and propagated Selenium failures; there is no verified universal exit contract.
- Exporter prints download/write failures and returns status 1 if decks fail; directory creation has its own error
  handling. Missing `APPDATA` in the default Forge path raises before that handling. Skipped overwrite prompts do not
  count as failed downloads. Forge catches and re-raises selected errors with debug focus behavior.
- Mana creator raises `ValueError` for duplicate/invalid colors. Its API helper prints non-200 errors and returns no
  cards, stores successful/no-result responses indefinitely, and reads only the first page. Vanilla raises HTTP
  errors, follows pagination, and does not cache. These are current behaviors, not endorsed shared-service policies.
- Plain file tools generally propagate file errors. Print Picker exposes resolution/errors through its UI and
  workers; no common CLI status contract exists for it.
- Print Picker caches JSON/images and schema-v5 SQLite data beside its package; bulk metadata has a 24-hour TTL,
  while ordinary JSON has no expiry. Mana creator separately hashes queries beside its source. Shared cache paths,
  expiry policy, and reader-safe deletion are later-phase changes, not part of this baseline.

## Gates for Later Phases

Keep existing behavior tests and add focused characterization immediately before extracting each owner. Import-safe
entry points are covered by the Phase 2 contracts. Browser/Forge checks must
remain explicitly selected and must not perform final purchasing actions. Default unit tests use temporary fixtures
and stub service boundaries; do not require live accounts, bulk downloads, or a display just to cover pure functions.

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run ty check
uv lock --check
```

Phase 1 does not add CI, normalize command flags, change application algorithms, or centralize application caches.
