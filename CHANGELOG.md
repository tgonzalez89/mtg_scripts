# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure.
- Phase 1 refactoring baseline: command compatibility inventory, existing fixture contracts, and test ownership notes.
- Strict pytest markers for network, browser, GUI, Windows, and memory integration tests, with a default Python HTTP/socket guard for unmarked tests.
- Guarded subprocess checks for every command's import/help/invalid-argument paths without optional automation dependencies, plus workflow/state-isolation fixtures.
- CardTrader JSON output directory selection and callable/configurable price-diff input handling.
- Shared plain card-list parsing and structured atomic JSON persistence, with offline compatibility and failure-cleanup fixtures.
- A transport-injected Moxfield service with shared wire types, ID normalization, payload validation, domain errors, and response cleanup; no persistent deck cache.
- Feature-local Cardmarket offer models and a metadata-preserving selection adapter.
- Per-user provider-namespaced cache paths with `MTG_SCRIPTS_CACHE_DIR` and Print Picker `--cache-dir` overrides.
- Versioned JSON freshness envelopes, atomic byte/JSON publication, process-safe cache/build locks, epoch invalidation, and bounded provider-configured HTTP retries/rate limiting.
- Lazy Print Picker legacy cache/database migration, last-known-good Scryfall fallback, safe generation retention, and streamed atomic bulk downloads.
- Concurrent-process cache-fill/Scryfall-build fixtures, HTTP-date retry handling, corrupt-entry recovery, and interrupted download coverage.
- Neutral Scryfall provider records, a reusable paginated search client, and a schema-v6 SQLite store retaining card payloads.
- Optional Oracle Tags bulk ingestion/indexing by slug and oracle ID, with a local `cards_for_tag` service API.
- Offline/stale search policies, one-hour negative-result caching, and provider service/store fixtures.
- Offline Phase 6 consumer fixtures for mana-base query/price semantics, vanilla ranking, and Scryfall service ownership.
- Phase 7 offline fixtures for base-deck output, purchase accounting, CardTrader policy, browser cleanup, Forge runtime config/OCR, mana-base recipe config, and Print Picker exports.

### Changed
- Organize existing tests under CLI, mana-base creator, and Print Picker directories without changing application behavior.
- Derive CLI adapter expectations from package metadata and correct the documented command list.
- Complete the RiftCodex set-date fixture so its set-mismatch test no longer requests live API data.
- Phase 2: replace runpy dispatch and module-scope workflows with lazy argv-aware command entry points and integer workflow statuses.
- Defer browser, keep-awake, and Forge automation/OCR dependencies until after argument validation; isolate Forge desktop code in a local runtime module.
- Make kebab-case mana options canonical while retaining underscore aliases and recipe override/status behavior.
- Default vanilla output to the working directory, preserving existing formats and Forge/XMage destinations.
- Phase 3: reuse common parsing/JSON and provider fetching without merging purchased-order/CSV/printing formats, purchase accounting, or deck rendering policies.
- Preserve Moxfield requests versus curl impersonation settings and command debug-file formatting while reporting malformed provider responses explicitly.
- Phase 4: compose Print Picker backends over shared cache/HTTP services; separate request/image invalidation from bulk metadata/database refresh and never delete prior DB generations during routine reads.
- Phase 5: move Scryfall bulk/store ownership into `services.scryfall`, preserve Print Picker selection policy in its adapter, and retain v5 files without treating them as compatible with v6.
- Phase 6: migrate mana-base and vanilla searches to the shared Scryfall service; complete pagination and require `--allow-stale-data` before using expired mana-base prices.
- Share one Scryfall service across Print Picker backend instances and wait for active workers before backend/service shutdown.
- Phase 7: separate feature-local EDHREC/deck-selection, purchase parsing/calculation, Cardmarket optimization, CardTrader policy/page, mana-base acquisition/filter/allocation, Forge OCR/session, and Print Picker export/download helpers; keep existing deck-exporter render functions and small utilities in place.
- Pass mana-base recipe presets and explicit creator overrides as a typed configuration rather than invoking the creator with reconstructed argv.
- Phase 8: remove mana-base underscore flag aliases and transitional Scryfall store/helper re-exports; use local Oracle Tag/name lookups and local filtering before API fallback; recursively index Oracle Tag parent/child relationships in schema v7; add Windows CI, package build/install, command-help, and strict pre-commit gates.
- Replace full Scryfall card JSON with explicit consumed fields in schema v8; use typed records for mana-base filtering and vanilla ranking, omit unused tag weights, and require a fresh database build without legacy schema compatibility.
