import re

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def handle_alert(driver, timeout=5, verbose=False) -> bool | None:
    """
    Wait for an alert message (success or error).
    Closes it if found and returns:
        True  -> success alert
        False -> error alert
        None  -> no alert found
    """
    try:
        # Wait for any alert (success or error)
        alert = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@class,'alert') and contains(@class,'alert-dismissible')]")
            )
        )

        # Determine if it's success or error
        classes = str(alert.get_attribute("class"))
        is_success = "alert-success" in classes
        is_error = "alert-danger" in classes

        # Close the alert if possible
        try:
            close_button = alert.find_element(By.XPATH, ".//button[@data-bs-dismiss='alert']")
            close_button.click()
        except Exception:
            if verbose:
                print("Couldn't find or click the close button on the alert.")

        if is_success:
            if verbose:
                print("Success alert detected and closed.")
            return True
        elif is_error:
            if verbose:
                print("Error alert detected and closed.")
            return False
        else:
            if verbose:
                print("Unknown alert type detected and closed.")
            return None

    except Exception:
        if verbose:
            print("No alert appeared within the timeout.")
        return None


def parse_number(text: str) -> int | float:
    if not text:
        return 0
    s = text.replace("\xa0", "").replace("€", "").strip()
    s = s.replace(" ", "")
    # Handle thousand separators like '1.234,56' -> '1234.56'
    s = s.replace(".", "").replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return 0
    num = m.group(0)
    return float(num) if "." in num else int(num)


def get_cart_price(driver) -> float:
    """Wait until cart price element is visible and return the float value."""
    cart_price_el = WebDriverWait(driver, 1).until(
        EC.presence_of_element_located((By.XPATH, "//a[@id='cart']//span[contains(text(),'€')]"))
    )
    cart_text = cart_price_el.text.strip()

    return float(parse_number(cart_text))
