Compares owned, purchased, wanted, and existing Moxfield decks to produce cards still needed for purchase.

`parsing.py` owns the collection CSV, purchased-order/plain-list, and exclusion-list adapters. `purchase_calculator.py`
returns an explicit calculation result and keeps grouped variants at their maximum counts, independent decks additive,
and the existing one-copy considering policy. The command module handles Moxfield transport, workflow order, and report files.
