Automates CardTrader optimization across selected languages while reusing a Firefox profile.

The command exposes `main(argv=None) -> int`; importing it or requesting `--help` does not load Selenium or launch Firefox.
Use `--output-dir PATH` to place `card_prices_by_lang.json`, `chosen_languages.json`, and `final_card_prices.json`
in a specific directory. The default remains the working directory. JSON schemas, selectors, and price-selection behavior are unchanged.
`policy.py` owns text chunking and language threshold parsing, `pricing.py` owns language choice and cent conversion, and
`page.py` owns CardTrader-specific dropdown and optimizer controls. The workflow closes its Firefox driver on success or
failure; automated lifecycle tests use a fake driver and do not run a real session.

The standalone `diff.py` is now import-safe and exposes `compare_prices` and `main`. Its defaults remain `en.json`,
`any.json`, and a 50-to-1000-cent inclusive difference; `--english`, `--any-language`, `--min-diff`, and `--max-diff` override them.
