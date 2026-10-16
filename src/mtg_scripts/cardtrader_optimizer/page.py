"""CardTrader page-specific controls, kept separate from pricing policy."""

# Selenium is imported at the action boundary so CLI imports remain safe.
# ruff: noqa: PLC0415

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver


class CardTraderPage:
    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    def check_select_all(self, *, select: bool = True, timeout: int = 10) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions
        from selenium.webdriver.support.ui import WebDriverWait

        header = WebDriverWait(self.driver, 10).until(
            expected_conditions.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
        )
        wait = WebDriverWait(header, timeout)
        checkbox = wait.until(expected_conditions.element_to_be_clickable((By.NAME, "check_all")))
        self.driver.execute_script("window.scrollTo(0, 0);")
        if (not checkbox.is_selected() and select) or (checkbox.is_selected() and not select):
            checkbox.click()
        time.sleep(0.5)

    def _set_row_values(self, selector: str, value: str, label: str, *, warn: bool) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import Select

        selects = self.driver.find_elements(By.CSS_SELECTOR, f'select[name="{selector}"]')
        for element in selects:
            select = Select(element)
            if select.first_selected_option.get_attribute("value") == value:
                continue
            self.driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", element)
            try:
                select.select_by_value(value)
            except OSError, RuntimeError, ValueError:
                if warn:
                    print(f"Warning: Couldn't select {label} '{value}'.")

    def _select_menu(self, button_id: str, option_text: str, *, timeout: int = 10, uppercase: bool = False) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions
        from selenium.webdriver.support.ui import WebDriverWait

        self.check_select_all()
        display_text = option_text.upper() if uppercase and option_text != "Any" else option_text
        header = WebDriverWait(self.driver, 10).until(
            expected_conditions.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
        )
        wait = WebDriverWait(header, timeout)
        button = wait.until(expected_conditions.element_to_be_clickable((By.ID, button_id)))
        self.driver.execute_script("window.scrollTo(0, 0);")
        button.click()
        option = wait.until(
            expected_conditions.element_to_be_clickable(
                (
                    By.XPATH,
                    f"//div[@aria-labelledby='{button_id}']//a[normalize-space()='{display_text}']",
                )
            )
        )
        option.click()
        time.sleep(0.25)
        self.check_select_all(select=False)
        time.sleep(0.25)

    def set_expansion(self, option_text: str, timeout: int = 10) -> None:
        self._select_menu("setExpansionButton", option_text, timeout=timeout)
        self._set_row_values("expansion", "" if option_text == "Any" else option_text, "expansion", warn=False)

    def set_language(self, option_text: str, timeout: int = 10) -> None:
        self._select_menu("setLanguageButton", option_text, timeout=timeout, uppercase=True)
        self._set_row_values("language", "" if option_text == "Any" else option_text, "language", warn=True)

    def set_condition(self, option_text: str, timeout: int = 10) -> None:
        self._select_menu("setConditionButton", option_text, timeout=timeout)
        self._set_row_values("condition", "" if option_text == "Any" else option_text, "condition", warn=True)

    def set_foil(self, option_text: str, timeout: int = 10) -> None:
        self._select_menu("setFoilButton", option_text, timeout=timeout)
        self._set_row_values("foil", "" if option_text == "Any" else option_text, "foil", warn=False)

    def click_button(self, button_name: str) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions
        from selenium.webdriver.support.ui import WebDriverWait

        button = WebDriverWait(self.driver, 10).until(
            expected_conditions.element_to_be_clickable(
                (
                    By.XPATH,
                    f"//button[contains(@class, 'btn') and contains(normalize-space(.), {button_name})]",
                )
            )
        )
        self.driver.execute_script("window.scrollTo(0, 0);")
        button.click()

    def wait_for_optimizer(self) -> None:
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions
        from selenium.webdriver.support.ui import WebDriverWait

        optimizer_xpath = (
            "//div[h5[contains(text(), 'CardTrader Zero')] and descendant::a[normalize-space(text())='Buy now']]"
        )
        container = WebDriverWait(self.driver, 10).until(
            expected_conditions.presence_of_element_located((By.XPATH, optimizer_xpath))
        )
        buy_now_link = container.find_element(By.XPATH, ".//a[normalize-space(text())='Buy now']")
        WebDriverWait(self.driver, 300).until(lambda _: buy_now_link.get_attribute("disabled") is None)
        self.driver.execute_script("window.scrollTo(0, 0);")
        ActionChains(self.driver).move_to_element(buy_now_link).perform()
        time.sleep(0.5)
