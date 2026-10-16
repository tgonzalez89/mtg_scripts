Builds a Commander mana base from deck colors and Scryfall land data.

Use kebab-case options, for example `mana_base_creator --colors WG --total-lands 40 --price-source eur`.
Underscore spellings are not accepted; group/specific-land selection and off-color flags also use kebab-case.

Both creator and recipe expose `main(argv=None) -> int`. Recipe positional arguments are unchanged;
extra options are appended after preset values so explicit overrides keep precedence, and the creator's status is returned.
Imports and `--help` do not query Scryfall. Queries now use the shared Scryfall search cache and fetch every result page;
previously truncated groups may therefore contain additional lands. The original source-local cache files are retained
but are no longer read. Cached search/price data expires after 24 hours; pass `--allow-stale-data` to permit an expired
price snapshot after a refresh failure, with a warning and timestamp.

Simple Oracle Tag groups and exact-name candidates are resolved from the local Scryfall SQLite store. Mana-base applies
paper/Commander legality, configured price-source, color, fetchland, and group-budget filters locally, then chooses the
lowest-priced eligible printing available in the local database for each oracle identity. The database uses the
currently indexed bulk printings, so this is not a guarantee of the cheapest printing across every Scryfall printing.
Groups with custom query syntax and names absent locally fall back to full cached Scryfall search; arbitrary syntax is
never approximated by a partial local query engine. If older bulk metadata has no Oracle Tags index, tag groups fall
back to API search.

`scryfall.py`, `candidate_acquisition.py`, `land_filter.py`, and `allocation.py` separate service access, candidate
reconciliation, card filtering, and budget/basic-land allocation. The recipe resolves its budget/theme preset plus
explicit creator overrides into a typed configuration before invoking the workflow.
