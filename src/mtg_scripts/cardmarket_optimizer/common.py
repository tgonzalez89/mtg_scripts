"""Shared Cardmarket browser helpers."""

import re
from typing import TYPE_CHECKING

from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver


def handle_alert(driver: WebDriver, timeout: int = 5, *, verbose: bool = False) -> bool | None:
    """Wait for an alert, close it, and classify its result.

    Returns ``True`` for success alerts, ``False`` for error alerts, and
    ``None`` when no alert appears or its type is unknown.
    """
    try:
        alert = WebDriverWait(driver, timeout).until(
            expected_conditions.presence_of_element_located(
                (By.XPATH, "//div[contains(@class,'alert') and contains(@class,'alert-dismissible')]")
            )
        )
    except TimeoutException:
        if verbose:
            print("No alert appeared within the timeout.")
        return None

    classes = str(alert.get_attribute("class"))
    is_success = "alert-success" in classes
    is_error = "alert-danger" in classes

    try:
        close_button = alert.find_element(By.XPATH, ".//button[@data-bs-dismiss='alert']")
        close_button.click()
    except NoSuchElementException, WebDriverException:
        if verbose:
            print("Couldn't find or click the close button on the alert.")

    if is_success:
        if verbose:
            print("Success alert detected and closed.")
        return True
    if is_error:
        if verbose:
            print("Error alert detected and closed.")
        return False
    if verbose:
        print("Unknown alert type detected and closed.")
    return None


def parse_number(text: str) -> int | float:
    """Parse a localized euro-formatted number."""
    if not text:
        return 0
    normalized = text.replace("\xa0", "").replace("€", "").replace(" ", "")
    normalized = normalized.replace(".", "").replace(",", ".")
    match = re.search(r"-?\d+(\.\d+)?", normalized)
    if not match:
        return 0
    number = match.group(0)
    return float(number) if "." in number else int(number)


def get_cart_price(driver: WebDriver) -> float:
    """Wait until the cart price is visible and return it as a float."""
    cart_price_element = WebDriverWait(driver, 1).until(
        expected_conditions.presence_of_element_located((By.XPATH, "//a[@id='cart']//span[contains(text(),'€')]"))
    )
    return float(parse_number(cart_price_element.text.strip()))
