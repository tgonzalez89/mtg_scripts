Builds a Commander starting deck from EDHREC data, applying synergy, inclusion, price, vendor, and theme filters.

The EDHREC transport subclass is isolated in `edhrec_client.py`; candidate qualification, price filtering, occurrence
counts, main/considering classification, and file rendering live in `deck_builder.py`. `build_base_deck.py` retains
argument parsing and workflow orchestration. Thresholds and the existing regular/budget occurrence rules are unchanged.
