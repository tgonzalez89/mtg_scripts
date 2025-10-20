import argparse
import json
import re
import time
from pathlib import Path

from filters import filters
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from wakepy import keep

# CLOSE FIREFOX BEFORE RUNNING THIS SCRIPT

"""
Steps to Locate Your Firefox Profile Folder:
1. Open Firefox.
2. In the address bar, type: about:profiles and press Enter.
3. You'll see a list of profiles. Look for the one labeled "Default" or the one you actively use.
4. Under that profile, find the "Root Directory" path.
"""

# TODO:
# Skip sellers that only provide tracked shipping (expensive)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--card-list", "-c", required=True, help="Path to a text file containing the card list (required)."
    )

    parser.add_argument("--username", "-u", required=True, help="Cardmarket username.")

    parser.add_argument("--password", "-p", required=True, help="Cardmarket password.")

    parser.add_argument(
        "--browser-profile",
        "-b",
        help="Path to Firefox profile. E.g. "
        r"C:\Users\<user>\AppData\Roaming\Firefox\Profiles\<random_string>.default-release",
    )

    parser.add_argument(
        "--max-editions",
        "-m",
        type=int,
        default=10,
        help="Max amount of editions that will be looked at, per wanted card.",
    )
    parser.add_argument(
        "--max-offers-per-edition",
        "-x",
        type=int,
        default=10,
        help="Max amount of card offers that will be looked at, per card edition.",
    )
    parser.add_argument(
        "--max-total-offers",
        "-t",
        type=int,
        default=100,
        help="Max amount of total card offers that will be looked at.",
    )

    args = parser.parse_args()
    return args


def get_cart_price(driver):
    """Wait until cart price element is visible and return the float value."""
    cart_price_el = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//a[@id='cart']//span[contains(text(),'€')]"))
    )
    cart_text = cart_price_el.text.strip()

    # Extract numeric value
    match = re.search(r"([\d,.]+)", cart_text)
    if match:
        return float(match.group(1).replace(".", "").replace(",", "."))
    else:
        return 0.0


sellers_database: dict[str, float] = {}
if Path("sellers_database.json").is_file():
    sellers_database = json.load(Path("sellers_database.json").open())


def empty_cart(driver: WebDriver, ret=True):
    # Empty cart
    driver.get("https://www.cardmarket.com/en/Magic/ShoppingCart")
    remove_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@value='Remove all articles']"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", remove_btn)
    remove_btn.click()
    # Wait for confirmation that cart is empty
    WebDriverWait(driver, 10).until_not(
        EC.presence_of_element_located((By.XPATH, "//input[@value='Remove all articles']"))
    )
    if ret:
        driver.back()


def get_row_data(row: WebElement):
    try:
        button = row.find_element(By.XPATH, ".//button[@aria-label='Put in shopping cart']")
    except NoSuchElementException:
        return None, None

    # Get the seller name
    seller_element = row.find_element(
        By.XPATH, ".//div[contains(@class,'col-sellerProductInfo')]//span[contains(@class,'seller-name')]//a"
    )
    seller_name = seller_element.text.strip()
    # Get the condition
    condition_element = row.find_element(
        By.XPATH,
        ".//div[contains(@class,'col-product')]//div[contains(@class,'product-attributes')]/a[contains(@class,'article-condition')]/span",
    )
    condition = condition_element.text.strip()
    # Get the language
    language_element = row.find_element(
        By.XPATH,
        ".//div[contains(@class,'col-product')]//div[contains(@class,'product-attributes')]/span[@aria-label]",
    )
    language = str(language_element.get_attribute("aria-label")).strip()
    # Get the amount
    amount_element = row.find_element(
        By.XPATH,
        ".//div[contains(@class,'col-offer')]//div[contains(@class,'amount-container')]//span",
    )
    amount = int(amount_element.text.strip())
    # Get the price
    card_element = row.find_element(
        By.XPATH,
        ".//div[contains(@class,'col-offer')]//div[contains(@class,'price-container')]//span[contains(text(),'€')]",
    )
    price = float(card_element.text.strip().replace("€", "").replace(".", "").replace(",", "."))

    clicked = False
    if seller_name not in sellers_database:
        # Get current cart price before clicking
        cart_price_before = get_cart_price(driver)
        # Click "Put in shopping cart"
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable(button)).click()
        clicked = True
        alert_result = handle_alert(driver)
        # Wait for cart price to change
        cart_price_after = cart_price_before
        while cart_price_before == cart_price_after and alert_result:
            # Get new total cart price
            try:
                cart_price_after = get_cart_price(driver)
            except StaleElementReferenceException:
                continue
            time.sleep(0.1)
        if (cart_price_before == cart_price_after) or (alert_result is not None and not alert_result):
            return None, clicked
        # Calculate total an shipping prices
        total_price = cart_price_after - cart_price_before
        shipping_price = total_price - price
        sellers_database[seller_name] = round(shipping_price, 2)
        json.dump(sellers_database, Path("sellers_database.json").open("w"), indent=2)
    else:
        shipping_price = sellers_database[seller_name]
        total_price = price + shipping_price

    return {
        "total_price": round(total_price, 2),
        "price": round(price, 2),
        "shipping_price": round(shipping_price, 2),
        "amount": amount,
        "seller": seller_name,
        "condition": condition,
        "language": language,
    }, clicked


def handle_alert(driver, timeout=1):
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
        classes = alert.get_attribute("class")
        is_success = "alert-success" in classes
        is_error = "alert-danger" in classes

        # Close the alert if possible
        try:
            close_button = alert.find_element(By.XPATH, ".//button[@data-bs-dismiss='alert']")
            close_button.click()
        except Exception:
            pass  # Ignore if already closed or not found

        if is_success:
            # print("Success alert detected and closed.")
            return True
        elif is_error:
            # print("Error alert detected and closed.")
            return False
        else:
            # print("Unknown alert type detected and closed.")
            return None

    except Exception:
        # print("No alert appeared within the timeout.")
        return None


with keep.presenting():
    args = parse_args()

    card_list: dict[str, int] = {}
    for line in Path(args.card_list).open().read().strip().split("\n"):
        amount_str, card_name = line.split(" ", maxsplit=1)
        card_list[card_name] = card_list.get(card_name, 0) + int(amount_str)

    options = Options()
    if args.browser_profile:
        options.add_argument("-profile")
        options.add_argument(args.browser_profile)
    driver = webdriver.Firefox(options=options)

    # --- Step 0: Log in ---
    driver.get("https://www.cardmarket.com/en/Magic")

    text_box = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@name='username']")))
    text_box.clear()
    text_box.send_keys(args.username)

    text_box = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@name='userPassword']")))
    text_box.clear()
    text_box.send_keys(args.password)

    login_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and contains(@class,'btn')]"))
    )
    login_button.click()
    account_dropdown = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "account-dropdown")))
    logged_in_username = account_dropdown.find_element(By.XPATH, ".//span[@class='d-none d-lg-block']").text
    print(f"Login successful! Logged in as: {logged_in_username}")

    offers_database: dict[str, list[dict[str, int | float | str]]] = {}
    if Path("offers_database.json").is_file():
        offers_database = json.load(Path("offers_database.json").open())

    if get_cart_price(driver) != 0:
        empty_cart(driver, ret=False)

    for card_num, card_name in enumerate(card_list, start=1):
        # --- Step 1: Search for card ---
        print(f"\nProcessing card {card_num}/{len(card_list)} '{card_name}'")
        driver.get("https://www.cardmarket.com/en/Magic/Products/Singles")

        search_box = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//label[normalize-space(text())='Name']/following-sibling::input[@name='searchString']")
            )
        )
        search_box.clear()
        search_box.send_keys(card_name)

        checkbox = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@name='exactMatch']"))
        )
        if not checkbox.is_selected():
            checkbox.click()

        checkbox = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@name='onlyAvailable']"))
        )
        if not checkbox.is_selected():
            checkbox.click()

        dropdown_element = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//select[@name='sortBy']"))
        )
        select = Select(dropdown_element)
        select.select_by_value("price_asc")

        search_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Search']"))
        )
        search_button.click()

        # --- Step 2: Collect card urls ---
        excluded_rarities = {"Special", "Token", "Code Card", "Tip Card"}

        rows = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located(
                (By.XPATH, "//div[@class='table-body']/div[contains(@id,'productRow')]")
            )
        )

        card_urls = []

        for row in rows:
            try:
                # Extract rarity (from the SVG's aria-label)
                rarity_element = row.find_element(
                    By.XPATH, ".//div[contains(@class,'col-sm-2')]/div/span/*[name()='svg' and @aria-label]"
                )
                rarity = str(rarity_element.get_attribute("aria-label")).strip()
                # Skip unwanted rarities
                if rarity in excluded_rarities:
                    continue

                # Extract name and link
                name_element = row.find_element(By.XPATH, ".//div[contains(@class,'col')]/div/div/div/a")
                url = str(name_element.get_attribute("href")).strip()
                url = url.split("?", maxsplit=1)[0]  # Remove any filters, if any.
                card_urls.append(url)
            except Exception as e:
                print(e)

        # Add filters to card urls
        card_urls_with_filters: list[str] = []
        for card_url in card_urls:
            filter_strings = []
            for name, value in filters.items():
                filter_string = name + "="
                if isinstance(value, list):
                    if len(value) > 0:
                        filter_string += ",".join(str(i) for i in value)
                        filter_strings.append(filter_string)
                elif value is not None:
                    filter_string += str(value)
                    filter_strings.append(filter_string)
            all_filters_string = "&".join(filter_strings)
            if len(all_filters_string) > 0:
                card_url += "?" + all_filters_string
            card_urls_with_filters.append(card_url)

        # --- Step 3: Visit each card page to get all the offers ---
        editions_limit = min(args.max_editions, len(card_urls_with_filters))
        per_edition_limit = max(args.max_offers_per_edition, (args.max_total_offers // editions_limit))
        print(f"DEBUG: {editions_limit=} {per_edition_limit=}")
        total_amount_offers = 0
        for edition_idx, url in enumerate(card_urls_with_filters):
            url_parts = url.split("?", maxsplit=1)[0].split("/")
            edition_name = url_parts[-2]
            print(f"Processing edition {edition_idx + 1}/{len(card_urls_with_filters)} '{edition_name}'")

            driver.get(url)

            # Get the details of all the offers
            offers: set = set()
            i = 0
            refresh_rows = True
            disappeared_rows = 0
            while len(offers) < per_edition_limit:
                # Find all rows inside the offers table
                if refresh_rows:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//section[@id='table']"))
                    )
                    rows = WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located(
                            (By.XPATH, "//div[@class='table-body']/div[contains(@id, 'articleRow')]")
                        )
                    )

                # Collect offer
                try:
                    row = rows[i]
                except IndexError:
                    break
                offer, clicked = get_row_data(row)
                if offer is None and clicked:
                    # Error adding to cart, try again.
                    refresh_rows = True
                    empty_cart(driver)
                    i += disappeared_rows
                    disappeared_rows = 0
                    continue
                if (offer is not None and clicked is not None) and (clicked and offer["amount"] == 1):
                    # Row disappeared.
                    # Rows disappear when "Put in shopping cart" is clicked and when amount in offer == 1.
                    disappeared_rows += 1
                    refresh_rows = True
                else:
                    i += 1
                    refresh_rows = False
                if offer is None:
                    continue
                offer["url"] = url.split("?", maxsplit=1)[0]
                offer = frozenset(offer.items())
                if offer not in offers:
                    tmp_dict = dict(offer)
                    tmp_dict.pop("url")
                    print(dict(sorted(tmp_dict.items())))
                offers.add(offer)
                total_amount_offers += 1

            if len(offers) > 0:
                if card_name not in offers_database:
                    offers_database[card_name] = []
                offers_database[card_name].extend(dict(offer) for offer in offers)

            # Stop if we reach the limit.
            if edition_idx + 1 >= args.max_editions or total_amount_offers >= args.max_total_offers:
                break

        if get_cart_price(driver) != 0:
            empty_cart(driver, ret=False)

        offers_database[card_name] = list(
            dict(offer) for offer in set(frozenset(offer.items()) for offer in offers_database[card_name])
        )
        json.dump(offers_database, Path("offers_database.json").open("w"), indent=2)

    driver.close()
