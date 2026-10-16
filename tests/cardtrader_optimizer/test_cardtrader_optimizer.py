from __future__ import annotations

from argparse import ArgumentTypeError, Namespace
from typing import TYPE_CHECKING, cast

import pytest
from selenium import webdriver

from mtg_scripts.cardtrader_optimizer import cardtrader_optimizer
from mtg_scripts.cardtrader_optimizer.policy import parse_language_thresholds, split_string_evenly
from mtg_scripts.cardtrader_optimizer.pricing import choose_languages3, price_per_card_cents

if TYPE_CHECKING:
    from pathlib import Path

    from selenium.webdriver.remote.webdriver import WebDriver


def test_language_threshold_and_text_chunk_policies() -> None:
    assert parse_language_thresholds("en:0,es:25,Any:100") == {"en": 0, "es": 25, "Any": 100}
    assert split_string_evenly("a\nb\nc\nd\ne", max_per_group=3) == [["a", "b", "c"], ["d", "e"]]
    with pytest.raises(ArgumentTypeError):
        parse_language_thresholds("en:10")


def test_language_choice_uses_incremental_and_accumulated_savings() -> None:
    prices = {
        "en": {"Card A": 100, "Card B": 50},
        "fr": {"Card A": 85},
        "de": {"Card A": 70, "Card B": 35},
    }

    assert choose_languages3(prices, {"en": 0, "fr": 10, "de": 20}) == {"Card A": "fr", "Card B": "en"}


def test_price_conversion_preserves_per_copy_cents() -> None:
    assert price_per_card_cents("€1,20", 2) == 60


def test_cardtrader_workflow_quits_browser_when_work_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeDriver:
        closed = False

        def quit(self) -> None:
            self.closed = True

    driver = FakeDriver()
    monkeypatch.setattr(webdriver, "Firefox", lambda **_kwargs: cast("WebDriver", driver))

    failure_message = "fixture failure"
    failure = RuntimeError(failure_message)

    def fail_work(_args: Namespace, _driver: WebDriver) -> None:
        raise failure

    monkeypatch.setattr(cardtrader_optimizer, "_run_with_driver", fail_work)
    with pytest.raises(RuntimeError, match=failure_message):
        cardtrader_optimizer._run(Namespace(output_dir=tmp_path, browser_profile=None))
    assert driver.closed
