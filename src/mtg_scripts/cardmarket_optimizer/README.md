Provides Cardmarket scraping, offer optimization, shopping-wizard automation, and dummy data generation.

Core offer fields are defined in `models.py`. `ScrapedOffer` adds condition/language and an optional URL;
`SelectedOfferRecord` adds optional selection fields and retains scraper metadata. `to_selected_offer` copies at
the optimizer's mutation boundary without dropping additional fields. Generated offer JSON retains its original five-field schema.

The optimizer, scraper, and generator use the shared plain-list and atomic JSON utilities where applicable.
Offer amounts, prices, shipping, tie-breaking, filenames, and JSON formatting remain unchanged.
Greedy offer scoring, seller availability, singleton-seller re-selection, totals, and the output report boundary live in
`optimization.py`. Cardmarket selectors, alert handling, locale number parsing, and Shopping Wizard page actions remain
feature-local; browser workflows own and close their driver even when a step fails. No real account or cart run is part
of the offline test suite.
