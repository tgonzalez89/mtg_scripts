from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING, Any

from mtg_scripts.build_base_deck import build_base_deck, deck_builder
from mtg_scripts.build_base_deck.edhrec_client import _normalize_average_decklist

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest


def _card_view(name: str) -> dict[str, Any]:
    return {"name": name, "lift": 5.0, "num_decks": 1, "potential_decks": 10}


def test_main_preserves_regular_budget_price_and_occurrence_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeEDHRec:
        def _build_nextjs_uri(
            self, endpoint: str, _commander: str, *, theme: str | None, budget: str | None
        ) -> tuple[tuple[str, str | None], dict[str, str | None]]:
            return (endpoint, budget), {"theme": theme}

        def _get(self, uri: tuple[str, str | None], *, query_params: dict[str, str | None]) -> object:
            return uri

        def _get_nextjs_data(self, response: tuple[str, str | None]) -> dict[str, Any]:
            endpoint, budget = response
            if endpoint == "commanders":
                names = (
                    ["Main Card", "Popular Pick", "Expensive Card"]
                    if budget is None
                    else [
                        "Main Card",
                        "Budget Only",
                    ]
                )
                cardlists = [{"cardviews": [_card_view(name) for name in names]}]
                return {"container": {"json_dict": {"cardlists": cardlists}}}
            names = ["Main Card", "Average Only"] if budget is None else ["Main Card", "Budget Average Only"]
            deck = {"cards": {"Other": [[name, 1] for name in names]}, "commander": ["Test Commander"]}
            return {"deck": deck}

        def get_card_list(self, names: list[str]) -> dict[str, Any]:
            return {
                "cards": {
                    name: {
                        "name": name,
                        "prices": {"cardkingdom": {"price": 30 if name == "Expensive Card" else 2}},
                    }
                    for name in names
                }
            }

    def identity_cache(function: Callable[..., Any]) -> Callable[..., Any]:
        return function

    fake_client_module = ModuleType("pyedhrec")
    fake_cache_module = ModuleType("pyedhrec.caching")
    fake_client_module.__dict__["EDHRec"] = FakeEDHRec
    fake_cache_module.__dict__["commander_cache"] = identity_cache
    fake_cache_module.__dict__["average_deck_cache"] = identity_cache
    fake_client_module.__dict__["caching"] = fake_cache_module
    monkeypatch.setitem(sys.modules, "pyedhrec", fake_client_module)
    monkeypatch.setitem(sys.modules, "pyedhrec.caching", fake_cache_module)
    monkeypatch.setattr(build_base_deck, "VERBOSE", False)
    output_path = tmp_path / "deck.txt"

    assert (
        build_base_deck.main(
            ["--commander-names", "Test Commander", "--price-threshold", "20", "--output-card-list", str(output_path)]
        )
        == 0
    )
    assert output_path.read_text(encoding="utf-8") == (
        "# MAIN DECK\nMain Card\n\n# CONSIDERING\nAverage Only\nBudget Average Only\nBudget Only\n"
        "Popular Pick\nTest Commander\n"
    )


def test_lift_threshold_accepts_values_above_one() -> None:
    args = build_base_deck.parse_args(["--commander-names", "Test Commander", "--lift-threshold", "4.5"])

    assert args.lift_threshold == 4.5


def test_average_deck_adapter_supports_legacy_and_plain_card_names() -> None:
    assert _normalize_average_decklist(["1 Arcane Signet", "Sol Ring"]) == ["Arcane Signet", "Sol Ring"]
    assert _normalize_average_decklist(
        {"cards": {"Creature": [["Grizzly Bears", 1]]}, "commander_v2": [["Test Commander", 1]]}
    ) == ["Grizzly Bears", "Test Commander"]


def test_card_eligibility_uses_lift_or_inclusion_not_synergy() -> None:
    cardlists = [
        {
            "cardviews": [
                {"name": "High Lift", "lift": 4.0, "num_decks": 1, "potential_decks": 100},
                {"name": "Popular", "num_decks": 20, "potential_decks": 100},
                {"name": "Synergy Only", "synergy": 1.0, "num_decks": 1, "potential_decks": 100},
                {"name": "Null Lift", "lift": None, "num_decks": 1, "potential_decks": 100},
            ]
        }
    ]

    cards = deck_builder.collect_eligible_cards(cardlists, lift_threshold=3.5, inclusion_threshold=0.15)

    assert set(cards) == {"High Lift", "Popular"}
