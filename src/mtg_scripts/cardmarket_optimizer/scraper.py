"""Steps to Locate Your Firefox Profile Folder.

1. Open Firefox.
2. In the address bar, type: about:profiles and press Enter.
3. You'll see a list of profiles. Look for the one labeled "Default" or the one you actively use.
4. Under that profile, find the "Root Directory" path.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

import argparse
import time
from pathlib import Path
from typing import TYPE_CHECKING, TypeIs, cast

from mtg_scripts.common.card_lists import parse_card_list
from mtg_scripts.common.json_io import read_json, write_json

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement

    from .models import ScrapedOffer


def _is_scraped_offer(value: object) -> TypeIs[ScrapedOffer]:
    return (
        isinstance(value, dict)
        and isinstance(value.get("total_price"), (int, float))
        and isinstance(value.get("price"), (int, float))
        and isinstance(value.get("shipping_price"), (int, float))
        and isinstance(value.get("amount"), int)
        and isinstance(value.get("seller"), str)
        and isinstance(value.get("condition"), str)
        and isinstance(value.get("language"), str)
        and ("url" not in value or isinstance(value["url"], str))
    )


def _load_sellers_database(path: Path) -> dict[str, float]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        message = f"Sellers database must contain an object: {path}"
        raise TypeError(message)
    result: dict[str, float] = {}
    for seller, shipping in payload.items():
        if not isinstance(seller, str) or not isinstance(shipping, (int, float)):
            message = f"Invalid seller database entry for {seller!r}"
            raise TypeError(message)
        result[seller] = float(shipping)
    return result


def _load_offers_database(path: Path) -> dict[str, list[ScrapedOffer]]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        message = f"Offers database must contain an object: {path}"
        raise TypeError(message)
    result: dict[str, list[ScrapedOffer]] = {}
    for card, offers in payload.items():
        if not isinstance(card, str) or not isinstance(offers, list):
            message = f"Invalid offers database entry for {card!r}"
            raise TypeError(message)
        records: list[ScrapedOffer] = []
        for offer in offers:
            if not _is_scraped_offer(offer):
                message = f"Invalid offer record for {card!r}"
                raise ValueError(message)
            records.append(offer)
        result[card] = records
    return result


def _offer_key(offer: ScrapedOffer) -> frozenset[tuple[str, int | float | str]]:
    fields: dict[str, int | float | str] = {
        "total_price": offer["total_price"],
        "price": offer["price"],
        "shipping_price": offer["shipping_price"],
        "amount": offer["amount"],
        "seller": offer["seller"],
        "condition": offer["condition"],
        "language": offer["language"],
    }
    if "url" in offer:
        fields["url"] = offer["url"]
    return frozenset(fields.items())


# CLOSE FIREFOX BEFORE RUNNING THIS SCRIPT

# TODO: Skip sellers that only provide tracked shipping (it's expensive)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--card-list",
        "-c",
        default="card_list.txt",
        help="Path to input text file containing the card list (default card_list.txt).",
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
        default=25,
        help="Max amount of editions that will be looked at, per wanted card (default 25).",
    )
    parser.add_argument(
        "--min-offers-per-edition",
        "-x",
        type=int,
        default=25,
        help="Min amount of card offers that will be looked at, per card edition (default 25).",
    )
    parser.add_argument(
        "--max-total-offers",
        "-t",
        type=int,
        default=500,
        help="Max amount of total card offers that will be looked at (default 500).",
    )
    parser.add_argument(
        "--sellers-database",
        "-s",
        default="sellers_database.json",
        help="Path to output sellers database file (default sellers_database.json).",
    )
    parser.add_argument(
        "--offers-database",
        "-o",
        default="offers_database.json",
        help="Path to output offers database file (default offers_database.json).",
    )

    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> None:
    from selenium import webdriver
    from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import Select, WebDriverWait
    from wakepy import keep

    from .common import get_cart_price, handle_alert
    from .scraper_filters import filters

    def empty_cart(driver: WebDriver, *, ret: bool = True) -> bool | None:
        # Empty cart
        driver.get("https://www.cardmarket.com/en/Magic/ShoppingCart")
        remove_btn = WebDriverWait(driver, 10).until(
            expected_conditions.element_to_be_clickable((By.XPATH, "//input[@value='Remove all articles']"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", remove_btn)
        driver.execute_script("arguments[0].click();", remove_btn)
        # Wait for confirmation that cart is empty
        try:
            WebDriverWait(driver, 10).until_not(
                expected_conditions.presence_of_element_located((By.XPATH, "//input[@value='Remove all articles']"))
            )
        except TimeoutException:
            return empty_cart(driver, ret=ret)
        if ret:
            driver.back()
        return None

    def get_row_data(row: WebElement, sellers_database: dict[str, float]) -> tuple[ScrapedOffer | None, bool]:
        try:
            button = row.find_element(By.XPATH, ".//button[@aria-label='Put in shopping cart']")
        except NoSuchElementException:
            return None, False

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
            driver.execute_script("arguments[0].scrollIntoView(true);", button)
            WebDriverWait(driver, 10).until(expected_conditions.element_to_be_clickable(button))
            driver.execute_script("arguments[0].click();", button)
            clicked = True
            alert_result = handle_alert(driver)
            # Wait for cart price to change
            cart_price_after = cart_price_before
            while cart_price_before == cart_price_after and bool(alert_result):
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

    with keep.presenting():
        sellers_database: dict[str, float] = {}
        if Path(args.sellers_database).is_file():
            sellers_database = _load_sellers_database(Path(args.sellers_database))

        offers_database: dict[str, list[ScrapedOffer]] = {}
        if Path(args.offers_database).is_file():
            offers_database = _load_offers_database(Path(args.offers_database))

        with Path(args.card_list).open("r", encoding="utf-8") as fp:
            card_list = parse_card_list(fp)

        options = Options()
        if args.browser_profile:
            options.add_argument("-profile")
            options.add_argument(args.browser_profile)
        driver = webdriver.Firefox(options=options)

        # --- Step 0: Accept cookies and log in ---
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

        text_box = WebDriverWait(driver, 10).until(
            expected_conditions.element_to_be_clickable((By.XPATH, "//input[@name='username']"))
        )
        text_box.clear()
        text_box.send_keys(args.username)

        text_box = WebDriverWait(driver, 1).until(
            expected_conditions.element_to_be_clickable((By.XPATH, "//input[@name='userPassword']"))
        )
        text_box.clear()
        text_box.send_keys(args.password)

        login_button = WebDriverWait(driver, 1).until(
            expected_conditions.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @title='Log in']"))
        )
        login_button.click()
        account_dropdown = WebDriverWait(driver, 10).until(
            expected_conditions.presence_of_element_located((By.ID, "account-dropdown"))
        )
        logged_in_username = account_dropdown.find_element(By.XPATH, ".//span[@class='d-none d-lg-block']").text
        print(f"Login successful! Logged in as: {logged_in_username}")

        if get_cart_price(driver) != 0:
            empty_cart(driver, ret=False)

        for card_num, card_name in enumerate(card_list, start=1):
            # --- Step 1: Search for card ---
            print(f"\nProcessing card {card_num}/{len(card_list)} '{card_name}'")
            driver.get("https://www.cardmarket.com/en/Magic/Products/Singles")

            search_box = WebDriverWait(driver, 10).until(
                expected_conditions.element_to_be_clickable(
                    (By.XPATH, "//label[normalize-space(text())='Name']/following-sibling::input[@name='searchString']")
                )
            )
            search_box.clear()
            search_box.send_keys(card_name)

            checkbox = WebDriverWait(driver, 1).until(
                expected_conditions.element_to_be_clickable((By.XPATH, "//input[@name='exactMatch']"))
            )
            if not checkbox.is_selected():
                checkbox.click()

            checkbox = WebDriverWait(driver, 1).until(
                expected_conditions.element_to_be_clickable((By.XPATH, "//input[@name='onlyAvailable']"))
            )
            if not checkbox.is_selected():
                checkbox.click()

            dropdown_element = WebDriverWait(driver, 1).until(
                expected_conditions.element_to_be_clickable((By.XPATH, "//select[@name='sortBy']"))
            )
            select = Select(dropdown_element)
            select.select_by_value("price_asc")

            search_button = WebDriverWait(driver, 1).until(
                expected_conditions.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Search']"))
            )
            search_button.click()

            # --- Step 2: Collect card urls ---
            excluded_rarities = {"Special", "Token", "Code Card", "Tip Card"}

            rows = WebDriverWait(driver, 1).until(
                expected_conditions.presence_of_all_elements_located(
                    (By.XPATH, "//div[@class='table-body']/div[contains(@id,'productRow')]")
                )
            )

            card_urls: list[str] = []

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
                except (OSError, RuntimeError, ValueError) as e:
                    print(e)

            # Add filters to card urls
            card_urls_with_filters: list[str] = []
            for raw_card_url in card_urls:
                card_url = raw_card_url
                filter_strings: list[str] = []
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
                    card_url = f"{card_url}?{all_filters_string}"
                card_urls_with_filters.append(card_url)

            # --- Step 3: Visit each card page to get all the offers ---
            if card_name not in offers_database:
                offers_database[card_name] = []
            editions_limit = min(args.max_editions, len(card_urls_with_filters))
            per_edition_limit = max(args.min_offers_per_edition, (args.max_total_offers // editions_limit))
            total_amount_offers = 0
            for edition_idx, url in enumerate(card_urls_with_filters):
                url_parts = url.split("?", maxsplit=1)[0].split("/")
                edition_name = url_parts[-2]
                print(f"Processing edition {edition_idx + 1}/{len(card_urls_with_filters)} '{edition_name}'")

                driver.get(url)

                # Get the details of all the offers
                offers: set[frozenset[tuple[str, int | float | str]]] = set()
                i = 0
                refresh_rows = True
                disappeared_rows = 0
                while len(offers) < per_edition_limit:
                    # Find all rows inside the offers table
                    if refresh_rows:
                        table = WebDriverWait(driver, 10).until(
                            expected_conditions.presence_of_element_located((By.XPATH, "//section[@id='table']"))
                        )
                        rows = table.find_elements(
                            By.XPATH, "//div[@class='table-body']/div[contains(@id, 'articleRow')]"
                        )

                    # Collect offer
                    try:
                        row = rows[i]
                    except IndexError:
                        break
                    offer, clicked = get_row_data(row, sellers_database)
                    if offer is None and clicked:
                        # Error adding to cart, try again.
                        refresh_rows = True
                        empty_cart(driver)
                        i += disappeared_rows
                        disappeared_rows = 0
                        continue
                    if offer is not None and clicked and offer["amount"] == 1:
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
                    offer_key = _offer_key(offer)
                    if offer_key not in offers:
                        tmp_dict = dict(offer_key)
                        tmp_dict.pop("url")
                        print(dict(sorted(tmp_dict.items())))
                    offers.add(offer_key)
                    total_amount_offers += 1

                if len(offers) > 0:
                    offers_database[card_name].extend(cast("ScrapedOffer", dict(offer)) for offer in offers)

                # Stop if we reach the limit.
                if edition_idx + 1 >= args.max_editions or total_amount_offers >= args.max_total_offers:
                    break

            # Uniquify offers.
            offers_database[card_name] = [
                cast("ScrapedOffer", dict(offer))
                for offer in {_offer_key(offer) for offer in offers_database[card_name]}
            ]

            write_json(Path(args.offers_database), offers_database)
            write_json(Path(args.sellers_database), sellers_database)

            if get_cart_price(driver) != 0:
                empty_cart(driver, ret=False)

        driver.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        from selenium.common.exceptions import WebDriverException
    except ImportError as error:
        print(str(error), file=sys.stderr)
        return 1
    try:
        _run(args)
    except (OSError, ValueError, RuntimeError, ImportError, WebDriverException) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
