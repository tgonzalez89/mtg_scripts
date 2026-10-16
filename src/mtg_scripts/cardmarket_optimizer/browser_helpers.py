"""Cardmarket page-specific login and cart actions for Shopping Wizard."""

# Selenium is imported at the action boundary so importing command modules remains safe.
# ruff: noqa: PLC0415

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from .common import get_cart_price, handle_alert

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver


def login_cardmarket(driver: WebDriver, username: str, password: str) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get("https://www.cardmarket.com/en/Magic")
    try:
        accept_button = WebDriverWait(driver, 2).until(
            expected_conditions.element_to_be_clickable(
                (By.XPATH, "//button[normalize-space(text())='Accept All Cookies']")
            )
        )
        accept_button.click()
    except OSError, RuntimeError, ValueError:
        pass

    username_box = WebDriverWait(driver, 10).until(
        expected_conditions.element_to_be_clickable((By.XPATH, "//input[@name='username']"))
    )
    username_box.clear()
    username_box.send_keys(username)

    password_box = WebDriverWait(driver, 1).until(
        expected_conditions.element_to_be_clickable((By.XPATH, "//input[@name='userPassword']"))
    )
    password_box.clear()
    password_box.send_keys(password)

    login_button = WebDriverWait(driver, 1).until(
        expected_conditions.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @title='Log in']"))
    )
    login_button.click()
    account_dropdown = WebDriverWait(driver, 10).until(
        expected_conditions.presence_of_element_located((By.ID, "account-dropdown"))
    )
    logged_in_username = account_dropdown.find_element(By.XPATH, ".//span[@class='d-none d-lg-block']").text
    print(f"Login successful! Logged in as: {logged_in_username}")


class CardmarketPage:
    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    def add_seller_to_cart(self, seller_name: str) -> None:
        from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException
        from selenium.webdriver.common.by import By

        seller_result_cards = self.driver.find_elements(By.CSS_SELECTOR, ".detailed-result-card")
        for result_card in seller_result_cards:
            seller_anchor = result_card.find_element(By.CSS_SELECTOR, ".seller-name a")
            if seller_anchor.text.strip() != seller_name:
                continue
            form = result_card.find_element(
                By.CSS_SELECTOR, "form[data-ajax-action='Wantslist_ShoppingWizard_AddArticlesToCart']"
            )
            button = form.find_element(By.CSS_SELECTOR, "button[type='submit']")
            cart_price_before = get_cart_price(self.driver)
            self.driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", button)
            while True:
                try:
                    button.click()
                    break
                except ElementClickInterceptedException:
                    time.sleep(0.5)
            cart_price_after = cart_price_before
            while cart_price_before == cart_price_after:
                try:
                    cart_price_after = get_cart_price(self.driver)
                except StaleElementReferenceException:
                    continue
                time.sleep(0.1)
            handle_alert(self.driver)
            break
