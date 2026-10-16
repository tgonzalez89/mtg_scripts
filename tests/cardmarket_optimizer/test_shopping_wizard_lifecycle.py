from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING, cast

import pytest
from selenium import webdriver

from mtg_scripts.cardmarket_optimizer import shopping_wizard_optimizer

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver


def test_shopping_wizard_quits_browser_when_work_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDriver:
        closed = False

        def quit(self) -> None:
            self.closed = True

    driver = FakeDriver()
    monkeypatch.setattr(webdriver, "Firefox", lambda **_kwargs: cast("WebDriver", driver))
    monkeypatch.setattr(shopping_wizard_optimizer.ShoppingWizardWorkflow, "login_setup", lambda _self: None)
    failure_message = "fixture failure"
    failure = RuntimeError(failure_message)

    def fail_work(_args: Namespace, _driver: WebDriver, _page: object) -> None:
        raise failure

    monkeypatch.setattr(shopping_wizard_optimizer, "_run_with_driver", fail_work)
    with pytest.raises(RuntimeError, match=failure_message):
        shopping_wizard_optimizer._run(Namespace(browser_profile=None))
    assert driver.closed
