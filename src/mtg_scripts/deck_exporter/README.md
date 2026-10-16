Downloads Moxfield deck data and exports it to Forge or XMage deck files.

`extract_deck_sections`, `format_card_list`, `format_xmage_card_list`, and the two file renderers remain the distinct
tested format boundaries. No additional `formats.py` layer was needed; Forge and XMage output destinations stay separate.
