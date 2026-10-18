Builds a Commander starting deck from EDHREC data, applying Lift, inclusion, price, vendor, and theme filters.

The EDHREC transport subclass is isolated in `edhrec_client.py`; candidate qualification, price filtering, occurrence
counts, main/considering classification, and file rendering live in `deck_builder.py`. `build_base_deck.py` retains
argument parsing and workflow orchestration. Lift has no fixed range; the default minimum is 0.5. The existing
inclusion and regular/budget occurrence rules are unchanged.
