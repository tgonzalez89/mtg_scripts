This directory contains the installable Python source package.

## Shared Boundaries

- [common/card_lists.py](mtg_scripts/common/card_lists.py): plain quantity/name parsing, aggregation, and matching keys. `parse_card_line` keeps the display name separate from the key; lowercase and first slash-separator behavior are retained for compatibility rather than applying new Unicode casefold collisions.
- [common/json_io.py](mtg_scripts/common/json_io.py): structured reads and atomic writes with caller-controlled formatting. No implicit directory creation, cache policy, or cross-process lock.
- [services/moxfield.py](mtg_scripts/services/moxfield.py): provider wire types, ID normalization, injected fetching, validation, and domain errors. It imports no feature modules and stores no deck snapshots.
- [services/scryfall/](mtg_scripts/services/scryfall/): typed Scryfall records, streaming bulk manager, compact v8 read-only SQLite store containing only consumed fields with recursive Oracle Tag hierarchy lookup, and complete cached API search. It does not import Print Picker or Tkinter.
- [common/cache.py](mtg_scripts/common/cache.py) and [common/http.py](mtg_scripts/common/http.py): `platformdirs` user-cache resolution, provider/category namespaces, versioned JSON envelopes, atomic byte/JSON publication, in-process coalescing, `filelock` interprocess coordination, epoch invalidation, provider-configured retries, throttling, and explicit session ownership.
- [cardmarket_optimizer/models.py](mtg_scripts/cardmarket_optimizer/models.py): core, scraped, and selected offer shapes plus a metadata-preserving copy adapter. This is not a cross-market schema.

Feature code may depend on common utilities and provider services; those shared layers must not import features.
Do not fold collection CSV, purchased-order paste, printing hints, or provider-specific browser behavior into the plain-list parser.
Moxfield transport adapters retain their existing request options; purchase accounting and deck renderers retain ownership of their own transformations.
Print Picker, mana-base creator, and vanilla use the shared Scryfall service and cache. Explicit cache roots override
`MTG_SCRIPTS_CACHE_DIR`, followed by the platform user-cache default. Print Picker's app owns a service shared across
backend instances while the adapter retains its printing policy locally. Mana-base and vanilla preserve their query
semantics and ranking/filtering logic; the service provides full pagination and cached transport.

Feature-local decompositions now keep provider adapters and policies beside their owning workflows: base-deck EDHREC
and deck selection, purchase parsing/calculation, Cardmarket optimization/page actions, CardTrader pricing/page
controls, mana-base acquisition/filter/allocation, Forge OCR/window session, and Print Picker export/download helpers.
Deck Exporter already exposes separate section extraction and Forge/XMage renderers; small standalone commands remain
function-oriented rather than gaining wrapper modules.
