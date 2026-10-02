from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING

from mtg_scripts.mana_base_creator import mana_base_creator

if TYPE_CHECKING:
    import pytest


def test_disabled_group_excludes_matching_cards_from_other_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    enabled_group = "otag:cycle-mh3-mdfc-dual-land"
    disabled_query = 'is:mdfc t:land -produces:m o:"This land enters tapped."'
    tapped_card: mana_base_creator.ScryfallCard = {
        "name": "Tapped MDFC",
        "oracle_text": "",
        "prices": {"eur": "1"},
    }
    other_card: mana_base_creator.ScryfallCard = {
        "name": "Other Candidate",
        "oracle_text": "",
        "prices": {"eur": "1"},
    }

    def populate_groups(groups: list[str], price_source: str) -> dict[str, list[mana_base_creator.ScryfallCard]]:
        if groups == [enabled_group]:
            return {enabled_group: [tapped_card, other_card]}
        return {disabled_query: [tapped_card]}

    monkeypatch.setattr(mana_base_creator, "populate_cards_from_groups", populate_groups)
    monkeypatch.setattr(mana_base_creator, "populate_cards_from_names", lambda names, price_source: [])
    args = Namespace(
        enable_groups=[enabled_group],
        disable_groups=[disabled_query],
        enable_specific_lands=[],
        disable_specific_lands=[],
        price_source="eur",
    )
    config = mana_base_creator.CardFilterConfig(
        colors="ur",
        price_source="eur",
        max_price_group_average=3,
        max_price_specific_lands=3,
        allow_off_color_lands=False,
    )

    groups, specific_lands = mana_base_creator._filter_candidates(args, config)

    assert groups == {enabled_group: {"Other Candidate": 1.0}}
    assert specific_lands == {}
