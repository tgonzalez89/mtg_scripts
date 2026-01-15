# TODO: Script that optimizes a 'wants' list.
# Input: cardmarket wants list id or maybe link?
# Algo should be something like this:
# Run the optimizer (input: filters, etc.)
# Add to the cart the cards from sellers that have many cards and that shipping not that expensive relative to the card cost
# Remove from the wants list the cards added to the card.
# Run the shopping wizard again and repeat the process.

# Ideas for criteria:
# First iteration:
# Only add to cart groups of cards that: a) have 3 or more cards and b) the price of the cards is at least half the price of the shipping
# Second iteration:
# Same as (1) but OR instead of AND (more flexible now)
# Third iteration:
# Add only groups that have 2 or more cards.
# Fourth iteration:
# No filters. By this point there's not much we can do.

# Record original,
# record total after optimizer and check which one is best

import argparse
import re
import time
from pprint import pprint

from common import get_cart_price, handle_alert, parse_number  # type:ignore[import-not-found]
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from shopping_wizard_optimizer_filter import filters  # type:ignore[import-not-found]

DEBUG = True

# CLOSE FIREFOX BEFORE RUNNING THIS SCRIPT

"""
Steps to Locate Your Firefox Profile Folder:
1. Open Firefox.
2. In the address bar, type: about:profiles and press Enter.
3. You'll see a list of profiles. Look for the one labeled "Default" or the one you actively use.
4. Under that profile, find the "Root Directory" path.
"""


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--wants-list-id",
        "-i",
        required=True,
        help="Unique identifier of the wants list. Get it from the url when you are in your wants list page (https://www.cardmarket.com/en/Magic/Wants/<id>).",
    )
    parser.add_argument("--username", "-u", required=True, help="Cardmarket username.")
    parser.add_argument("--password", "-p", required=True, help="Cardmarket password.")
    parser.add_argument(
        "--browser-profile",
        "-b",
        help="Path to Firefox profile. E.g. "
        r"C:\Users\<user>\AppData\Roaming\Firefox\Profiles\<random_string>.default-release",
    )

    args = parser.parse_args()
    return args


def add_seller_to_cart(driver: WebDriver, seller_name: str):
    seller_result_cards = driver.find_elements(By.CSS_SELECTOR, ".detailed-result-card")
    for result_card in seller_result_cards:
        seller_anchor = result_card.find_element(By.CSS_SELECTOR, ".seller-name a")
        result_card_seller_name = seller_anchor.text.strip()
        if result_card_seller_name != seller_name:
            continue
        # Get button.
        form = result_card.find_element(
            By.CSS_SELECTOR, "form[data-ajax-action='Wantslist_ShoppingWizard_AddArticlesToCart']"
        )
        button = form.find_element(By.CSS_SELECTOR, "button[type='submit']")
        # Get current cart price before clicking.
        cart_price_before = get_cart_price(driver)
        # Click "Put in shopping cart".
        driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", button)
        while True:
            try:
                button.click()
                break
            except ElementClickInterceptedException:
                time.sleep(0.5)
        # Wait for cart price to change.
        cart_price_after = cart_price_before
        while cart_price_before == cart_price_after:
            # Get new total cart price.
            try:
                cart_price_after = get_cart_price(driver)
            except StaleElementReferenceException:
                continue
            time.sleep(0.1)
        handle_alert(driver)
        break  # Break after finding the seller.


args = parse_args()


options = Options()
if args.browser_profile:
    options.add_argument("-profile")
    options.add_argument(args.browser_profile)
driver = webdriver.Firefox(options=options)

# --- Step 0: Accept cookies and log in ---
driver.get("https://www.cardmarket.com/en/Magic")

try:
    accept_button = WebDriverWait(driver, 2).until(
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(text())='Accept All Cookies']"))
    )
    accept_button.click()
except Exception:
    pass

text_box = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@name='username']")))
text_box.clear()
text_box.send_keys(args.username)

text_box = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.XPATH, "//input[@name='userPassword']")))
text_box.clear()
text_box.send_keys(args.password)

login_button = WebDriverWait(driver, 1).until(
    EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @title='Log in']"))
)
login_button.click()
account_dropdown = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "account-dropdown")))
logged_in_username = account_dropdown.find_element(By.XPATH, ".//span[@class='d-none d-lg-block']").text
print(f"Login successful! Logged in as: {logged_in_username}")

# --- Optimizer: Run the Shopping Wizard iteratively ---

# Results per iteration.
# Results in index 0 are the results we want to compare against at the end,
# since they are the original results for the whole Wants List.
results_overall_summaries: list[dict[str, int | float]] = []
"""
[
  {
    "wanted-articles": 99,
    "shipments": 22,
    "articles-value": 68.90,
    "shipping-cost": 48.27,
    "total": 118.17,
  },
  ...
]
"""
results_summaries_per_seller: list[dict[str, dict[str, int | float]]] = []
"""
[
  {
    "seller_name_1": {
      "wanted-articles": 13,
      "articles-value": 22.19,
      "shipping-cost": 2.10,
      "total": 24.29,
    },
    ...
  },
  ...
]
"""
results_details_per_seller: list[dict[str, list[dict[str, int | float | str | None]]]] = []
"""
[
  {
    "seller_name_1": [
      {
        "quantity": 1,
        "card-name": "Monstrous Vortex",
        "expansion": "Modern Horizons 3",
        "language": "English",
        "condition": "Near Mint",
        "price": 0.07,
      },
      ...
    ],
    ...
  },
  ...
]
"""

# Final results after optimization.
shopping_cart_overall_summary: dict[str, int | float] = {}
"""
{
  "shipments": 22,
  "wanted-articles": 99,
  "articles-value": 68.90,
  "shipping-cost": 48.27,
  "trustee-service": 0.08,
  "total": 118.17,
}
"""
shopping_cart_summaries_per_seller: dict[str, dict[str, int | float]] = {}
"""
{
  "seller_name_1": {
    "wanted-articles": 13,
    "articles-value": 22.19,
    "shipping-cost": 2.10,
    "trustee-service": 0.03,
    "total": 24.29,
  },
  ...
}
"""
shopping_cart_details_per_seller: dict[str, list[dict[str, int | float | str | None]]] = {}
"""
{
  "seller_name_1": [
    {
      "quantity": 1,
      "card-name": "Monstrous Vortex",
      "expansion": "Modern Horizons 3",
      "language": "English",
      "condition": "Near Mint",
      "extra": None,
      "price": 0.07,
    },
    ...
  ],
  ...
}
"""
cart_has_items = True
iteration_num = 0
while cart_has_items:
    print(f"\n=== Iteration {iteration_num + 1} ===")
    # --- Step 1: Go to Shopping Wizard for the Wants List ---
    driver.get(f"https://www.cardmarket.com/en/Magic/Wants/ShoppingWizard?idWantsList={args.wants_list_id}")

    done = False
    while not done:
        try:
            # Wait for the 'Select a Wants List' step to be visible.
            select_wants_list_section = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//section[h2[text()='Select a Wants List'] and not(contains(@style, 'display: none'))]")
                )
            )

            # Find and click the 'Next' button inside this visible section.
            next_button = WebDriverWait(select_wants_list_section, 5).until(
                EC.element_to_be_clickable((By.XPATH, ".//button[contains(@class, 'next-btn')]"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            next_button.click()
            done = True
        except ElementClickInterceptedException:
            print("Warning: Error while clicking the 'Next' button. Trying again.")

    # --- Step 2: Select filters ---
    select_options_section = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located(
            (By.XPATH, "//section[h2[text()='Select Your Options'] and not(contains(@style, 'display: none'))]")
        )
    )

    # Seller Country (multi-select).
    # Click the dropdown to open the menu.
    dropdown = select_options_section.find_element(By.ID, "sellerCountry")
    driver.execute_script("arguments[0].scrollIntoView(true);", dropdown)
    dropdown.click()
    # Wait until any .list-container under the dropdown becomes visible.
    list_container = WebDriverWait(driver, 5).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "#sellerCountry .list-container.show"))
    )
    # Find all <li> options inside the visible list.
    opts = list_container.find_elements(By.TAG_NAME, "li")
    # Click the one with the desired value.
    for opt in opts:
        value: int | str | None = opt.get_attribute("data-option-value")
        if str(value).isdigit():
            value = int(str(value))
        if value in filters.get("sellerCountry", []):
            driver.execute_script("arguments[0].scrollIntoView(true);", opt)
            try:
                opt.click()
            except ElementNotInteractableException:
                pass  # It was already selected.
    ActionChains(driver).move_to_element(dropdown).move_by_offset(
        dropdown.size["width"] - 5, dropdown.size["height"] // 2
    ).click().perform()

    # Seller Type (checkboxes).
    for seller_type in filters.get("sellerType", []):
        try:
            elem = select_options_section.find_element(
                By.CSS_SELECTOR, f"input[name='sellerType[{seller_type}]'][value='{seller_type}']"
            )
            if not elem.is_selected():
                elem.click()
        except Exception:
            pass

    # Seller Reputation (dropdown).
    try:
        reputation_select = Select(select_options_section.find_element(By.ID, "sellerReputation"))
        reputation_select.select_by_value(str(filters.get("sellerReputation")))
    except Exception:
        pass

    # Max Shipping Time (dropdown).
    try:
        shipping_select = Select(select_options_section.find_element(By.ID, "maxShippingTime"))
        shipping_select.select_by_value(str(filters.get("maxShippingTime")))
    except Exception:
        pass

    # Click 'Next' for this step.
    next_button = WebDriverWait(select_options_section, 5).until(
        EC.element_to_be_clickable((By.XPATH, ".//button[contains(@class, 'next-btn')]"))
    )
    driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
    next_button.click()

    # --- Step 3: Choose strategy and run ---
    strategy_section = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located(
            (
                By.XPATH,
                "//section[h2[text()='Choose Shopping Wizard Strategy'] and not(contains(@style, 'display: none'))]",
            )
        )
    )

    # Select the "Reduce Price" radio button.
    reduce_price_radio_btn = strategy_section.find_element(
        By.XPATH, ".//div[.//h3[text()='Reduce Price']]//input[@type='radio' and @name='strategy']"
    )
    reduce_price_radio_btn_id = reduce_price_radio_btn.get_attribute("id")
    label = WebDriverWait(strategy_section, 5).until(
        EC.element_to_be_clickable((By.XPATH, f".//label[@for='{reduce_price_radio_btn_id}']"))
    )
    driver.execute_script("arguments[0].scrollIntoView(true);", label)
    label.click()

    # Click 'Run Wizard'.
    run_wizard_button = WebDriverWait(strategy_section, 5).until(
        EC.element_to_be_clickable((By.XPATH, ".//button[contains(., 'Run Wizard')]"))
    )
    driver.execute_script("arguments[0].scrollIntoView(true);", run_wizard_button)
    run_wizard_button.click()

    # --- Step 4: Wait for Shopping Wizard to run ---
    # Wait until the wizard finishes and the browser navigates to the ShoppingWizard results page.
    # The URL looks like: https://www.cardmarket.com/en/Magic/Wants/ShoppingWizard/Results/<id>
    WebDriverWait(driver, 300).until(
        lambda d: d.current_url if "/Wants/ShoppingWizard/Results/" in d.current_url else False
    )

    # --- Step 5: Extract information ---
    # --- Step 5a: Get the Shopping Wizard Results Summary ---
    summary_container = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "ShoppingWizardResult")))
    dt_elems = summary_container.find_elements(By.TAG_NAME, "dt")
    dd_elems = summary_container.find_elements(By.TAG_NAME, "dd")
    overall_summary: dict[str, int | float] = {}
    for dt, dd in zip(dt_elems, dd_elems):
        key = dt.text.strip().lower().replace(" ", "-")
        if not key:
            continue
        val = parse_number(dd.text.strip())
        overall_summary[key] = val
    results_overall_summaries.append(overall_summary)

    # --- Step 5b: Per seller: extract summaries and details (articles list) ---
    summaries_per_seller: dict[str, dict[str, int | float]] = {}
    details_per_seller: dict[str, list[dict[str, int | float | str | None]]] = {}

    seller_result_cards = driver.find_elements(By.CSS_SELECTOR, ".detailed-result-card")

    for result_card in seller_result_cards:
        seller_anchor = result_card.find_element(By.CSS_SELECTOR, ".seller-name a")
        seller_name = seller_anchor.text.strip()

        # Extract the summary for this seller.
        summary: dict[str, int | float] = {}
        dl = result_card.find_element(By.TAG_NAME, "dl")
        dt_elems = dl.find_elements(By.TAG_NAME, "dt")
        dd_elems = dl.find_elements(By.TAG_NAME, "dd")
        for dt, dd in zip(dt_elems, dd_elems):
            key = dt.text.strip().lower().replace(" ", "-")
            if not key:
                continue
            val = parse_number(dd.text.strip())
            summary[key] = val
        summaries_per_seller[seller_name] = summary

        # Extract the details (articles list) for this seller.
        details: list[dict[str, int | float | str | None]] = []
        rows = result_card.find_elements(By.CSS_SELECTOR, "table tbody tr")
        for row in rows:
            article_details: dict[str, int | float | str | None] = {}
            tds = row.find_elements(By.TAG_NAME, "td")
            # Quantity is in the 3rd td (index 2).
            qty_elem = tds[2]
            article_details["quantity"] = parse_number(qty_elem.text)
            # Card name is in the 4th td (index 3).
            card_name_elem = tds[3]
            article_details["card_name"] = re.sub(r"\s*\(V\.\d+\)$", "", card_name_elem.text)
            # Expansion is in the 5th td (index 4).
            exp_elem = tds[4].find_element(By.CSS_SELECTOR, ".expansion-symbol")
            article_details["expansion"] = exp_elem.get_attribute("data-bs-original-title")
            # Language is in the 6th td (index 5).
            lang_elem = tds[5].find_element(By.CSS_SELECTOR, ".icon")
            article_details["language"] = lang_elem.get_attribute("data-bs-original-title")
            # Condition is in the 7th td (index 6).
            cond_elem = tds[6].find_element(By.CSS_SELECTOR, ".article-condition")
            article_details["condition"] = cond_elem.get_attribute("data-bs-original-title")
            # Price is in the 9th td (index 8).
            price_elem = tds[8]
            article_details["price"] = parse_number(price_elem.text)
            details.append(article_details)
        details_per_seller[seller_name] = details

    results_summaries_per_seller.append(summaries_per_seller)
    results_details_per_seller.append(details_per_seller)

    # --- Step 6: Add to cart sellers with good value ---
    cards_added_to_cart: dict[str, int] = {}
    strategy = 0
    sellers_added = 0
    while not cards_added_to_cart:
        for seller_name, summary in summaries_per_seller.items():
            add_seller = False
            match strategy:
                case 0:
                    # Only add to cart groups of cards that:
                    # a) have 4 or more cards AND
                    # b) the price of the cards is at least the price of the shipping
                    if summary["wanted-articles"] >= 4 and summary["articles-value"] >= summary["shipping-cost"]:
                        add_seller = True
                case 1:
                    # Same as (0) but OR instead of AND (more flexible now).
                    if summary["wanted-articles"] >= 4 or summary["articles-value"] >= summary["shipping-cost"]:
                        add_seller = True
                case 2:
                    # Same as (0) but with 2 or more cards and half the shipping cost.
                    if summary["wanted-articles"] >= 2 and summary["articles-value"] >= 0.5 * summary["shipping-cost"]:
                        add_seller = True
                case 3:
                    # Same as (2) but OR instead of AND (more flexible now).
                    if summary["wanted-articles"] >= 2 or summary["articles-value"] >= 0.5 * summary["shipping-cost"]:
                        add_seller = True
                case _:
                    # No filters. By this point there's not much we can do.
                    add_seller = True
            if add_seller:
                sellers_added += 1
                print(
                    f"Adding {len(results_details_per_seller[iteration_num][seller_name])} articles to cart from seller '{seller_name}'. Used strategy {strategy}."
                )
                add_seller_to_cart(driver, seller_name)
                for article in results_details_per_seller[iteration_num][seller_name]:
                    assert isinstance(article["quantity"], int)
                    cards_added_to_cart[str(article["card_name"])] = cards_added_to_cart.get(
                        str(article["card_name"]), 0
                    ) + int(article["quantity"])
        strategy += 1

    if sellers_added == len(summaries_per_seller):
        print(f"DEBUG: {results_details_per_seller[iteration_num]=}")
        print(f"DEBUG: {summaries_per_seller=}")
        cart_has_items = False

    if DEBUG:
        print(f"DEBUG: {iteration_num=} {len(cards_added_to_cart)=}")
        pprint(cards_added_to_cart)

    # --- Step 7: Remove cards added to cart from Wants List ---
    driver.get(f"https://www.cardmarket.com/en/Magic/Wants/{args.wants_list_id}")

    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "WantsListTable")))

    current_wants_list: dict[str, int] = {}
    rows = []
    while len(rows) == 0:
        time.sleep(0.5)
        rows = driver.find_element(By.ID, "WantsListTable").find_elements(By.CSS_SELECTOR, "table tbody tr[role='row']")
    if DEBUG:
        print(f"DEBUG: {len(rows)=}")
    for row in rows:
        tds = row.find_elements(By.TAG_NAME, "td")
        # Quantity is in the 3rd td (index 2).
        qty_elem = tds[2]
        qty = parse_number(qty_elem.text)
        # Card name is in the 4th td (index 3).
        card_name_elem = tds[3]
        card_name = re.sub(r"\s*\(V\.\d+\)$", "", card_name_elem.text)
        current_wants_list[card_name] = int(qty)
    if DEBUG:
        print(f"DEBUG: {iteration_num=} {len(current_wants_list)=}")
        pprint(current_wants_list)
    print(f"Found {len(current_wants_list)} elements in current Wants List.")

    new_wants_list: dict[str, int] = {}
    for card_name, wants_list_qty in current_wants_list.items():
        qty_to_remove = cards_added_to_cart.get(card_name, 0)
        new_qty = wants_list_qty - qty_to_remove
        if new_qty > 0:
            new_wants_list[card_name] = new_qty
    if DEBUG:
        print(f"DEBUG: {iteration_num=} {len(new_wants_list)=}")
        pprint(new_wants_list)
    print(f"Removing {len(cards_added_to_cart)} elements rom Wants List that were added to the cart.")
    print(f"Filtered Wants List will now have {len(new_wants_list)} elements.")

    # TODO: Change methodology.
    # Instead of removing all cards and re-adding the new, smaller wants list,
    # only remove the cards that were added to the cart.
    # This way we avoid losing the filters already set in the cards in the wants list.

    # Select all cards by selecting the "check all" checkbox
    checkbox = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//input[@name='checkAll']")))
    if not checkbox.is_selected():
        driver.execute_script("arguments[0].scrollIntoView(true);", checkbox)
        checkbox.click()
    # Delete selected cards.
    button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "deleteSelected")))
    button.click()
    # Wait for dismissible alert.
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[contains(@class,'alert') and contains(@class,'alert-dismissible')]")
        )
    )
    if len(new_wants_list) == 0:
        break
    # Click the Add Deck List button.
    button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//a[contains(@href,'/AddDeckList')]"))
    )
    button.click()
    # Wait for page to load.
    textarea = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "AddDecklist")))
    # Fill the textarea with the new wants list.
    wants_list_text = ""
    for card_name, qty in new_wants_list.items():
        wants_list_text += f"{qty} {card_name}\n"
    textarea.clear()
    textarea.send_keys(wants_list_text)
    # Click the add button.
    button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and contains(@class,'btn-success')]"))
    )
    button.click()
    # Wait for success alert.
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@class,'alert') and contains(@class,'alert-dismissible')]")
            )
        )
    except TimeoutException:
        print("Warning: No success alert after adding new wants list.")

    iteration_num += 1

# --- Step 8: Show a comparison of the prices before and after the optimizer ---
driver.get("https://www.cardmarket.com/en/Magic/ShoppingCart")

# 1) shopping_cart_overall_summary: parse the cart overview.
cart_overview_elem = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, ".cart-overview"))
)
shopping_cart_overall_summary = {}
label_map_overall_summary = {
    "Number of orders": "shipments",
    "Amount of articles": "wanted-articles",
    "Article Value": "articles-value",
    "Shipping": "shipping-cost",
    "Trustee Service": "trustee-service",
    "Total": "total",
}
# Find all d-flex rows inside the cart overview and pick values by label
rows = cart_overview_elem.find_elements(By.CSS_SELECTOR, "div.d-flex")
for row in rows:
    spans = row.find_elements(By.TAG_NAME, "span")
    label_text = spans[0].text.strip()
    value_text = spans[1].text.strip()
    mapped_key = label_map_overall_summary.get(label_text)
    if mapped_key is not None:
        shopping_cart_overall_summary[mapped_key] = parse_number(value_text)
if DEBUG:
    print(f"DEBUG: {shopping_cart_overall_summary}=")

# 2) shopping_cart_summaries_per_seller and 3) shopping_cart_details_per_seller: parse each seller section.
WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "section.shipment-block")))
seller_sections = driver.find_elements(By.CSS_SELECTOR, "section.shipment-block")
for section in seller_sections:
    seller_anchor = section.find_element(By.CSS_SELECTOR, ".seller-name a")
    seller_name = seller_anchor.text.strip()
    if DEBUG:
        print(f"DEBUG: {seller_name=}")
    # 2) Parse seller summary.
    data_attrs = section.find_element(By.CSS_SELECTOR, "div.summary").get_attribute("outerHTML")
    assert data_attrs is not None
    data_article_count = re.sub(r'.*data-article-count="([\d\.]+)".*', r"\1", data_attrs)
    data_item_value = re.sub(r'.*data-item-value="([\d\.]+)".*', r"\1", data_attrs)
    data_total_price = re.sub(r'.*data-total-price="([\d\.]+)".*', r"\1", data_attrs)
    data_shipping_price = re.sub(r'.*data-shipping-price="([\d\.]+)".*', r"\1", data_attrs)
    data_internal_insurance = re.sub(r'.*data-internal-insurance="([\d\.]+)".*', r"\1", data_attrs)
    data_vat_payment = re.sub(r'.*data-vat-payment="([\d\.]+)".*', r"\1", data_attrs)
    shopping_cart_summaries_per_seller[seller_name] = {}
    shopping_cart_summaries_per_seller[seller_name]["wanted-articles"] = int(data_article_count)
    shopping_cart_summaries_per_seller[seller_name]["articles-value"] = float(data_item_value)
    shopping_cart_summaries_per_seller[seller_name]["total"] = float(data_total_price)
    shopping_cart_summaries_per_seller[seller_name]["shipping-cost"] = float(data_shipping_price)
    shopping_cart_summaries_per_seller[seller_name]["trustee-service"] = float(data_internal_insurance)
    shopping_cart_summaries_per_seller[seller_name]["vat-payment"] = float(data_vat_payment)
    if DEBUG:
        print(f"DEBUG: {shopping_cart_summaries_per_seller[seller_name]=}")

    # 3) Parse seller details (articles list).
    table = section.find_element(By.CSS_SELECTOR, "table[id^='ArticleTable']")
    rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
    for row in rows:
        data_attrs = row.get_attribute("outerHTML")
        assert data_attrs is not None
        data_amount = re.sub(r'.*data-amount="([^"]+)".*', r"\1", data_attrs)
        data_name = re.sub(r'.*data-name="([^"]+)".*', r"\1", data_attrs)
        data_expansion_name = re.sub(r'.*data-expansion-name="([^"]+)".*', r"\1", data_attrs)
        data_price = re.sub(r'.*data-price="([\d\.]+)".*', r"\1", data_attrs)
        data_language = re.sub(r'.*data-language="([^"]+)".*', r"\1", data_attrs)
        data_condition = re.sub(r'.*data-condition="([^"]+)".*', r"\1", data_attrs)
        language_map = {
            "1": "English",
            "2": "French",
            "3": "German",
            "4": "Spanish",
            "5": "Italian",
            "6": "S-Chinese",
            "7": "Japanese",
            "8": "Portuguese",
            "9": "Russian",
            "10": "Korean",
            "11": "T-Chinese",
        }
        data_language_str = language_map.get(data_language, "Unknown")
        # Convert condition number to string.
        condition_map = {
            "1": "Mint",
            "2": "Near Mint",
            "3": "Excellent",
            "4": "Good",
            "5": "Light Played",
            "6": "Played",
            "7": "Poor",
        }
        data_condition_str = condition_map.get(data_condition, "Unknown")
        article_details = {
            "card-name": data_name,
            "quantity": int(data_amount),
            "expansion": data_expansion_name,
            "language": data_language_str,
            "condition": data_condition_str,
            "price": float(data_price),
        }
        shopping_cart_details_per_seller.setdefault(seller_name, []).append(article_details)
    if DEBUG:
        print(f"DEBUG: {shopping_cart_details_per_seller[seller_name]=}")

# Print shopping cart summaries.
print("\n--- Shopping cart overall summary ---")
for k, v in shopping_cart_overall_summary.items():
    print(f"{k}: {v}")

print("\n--- Shopping cart summaries per seller ---")
for seller, summ in shopping_cart_summaries_per_seller.items():
    print(f"Seller: {seller}")
    for k, v in summ.items():
        print(f"  {k}: {v}")

print("\n--- Shopping cart details per seller ---")
for seller, details in shopping_cart_details_per_seller.items():
    print(f"Seller: {seller} -> {len(details)} articles")
    for art in details:
        print(f"  {art}")

# Comparison vs original shopping wizard (index 0).
print("\n--- Comparison: Shopping Wizard original (index 0) vs Shopping Cart (final) ---")
if len(results_overall_summaries) > 0:
    original = results_overall_summaries[0]
    final = shopping_cart_overall_summary
    keys = set(list(original.keys()) + list(final.keys()))
    for key in sorted(keys):
        orig_val = original.get(key)
        final_val = final.get(key)
        diff = None
        try:
            if orig_val is None or final_val is None:
                diff = None
            else:
                diff = final_val - orig_val
        except Exception:
            diff = None
        print(f"{key}: original={orig_val} final={final_val} diff={diff}")
else:
    print("No original Shopping Wizard summary (results_overall_summaries is empty).")
