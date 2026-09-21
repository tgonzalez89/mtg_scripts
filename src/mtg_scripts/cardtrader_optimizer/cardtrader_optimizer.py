"""Steps to Locate Your Firefox Profile Folder.

1. Open Firefox.
2. In the address bar, type: about:profiles and press Enter.
3. You'll see a list of profiles. Look for the one labeled "Default" or the one you actively use.
4. Under that profile, find the "Root Directory" path.
"""

import argparse
import json
import re
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import Select, WebDriverWait

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver

# CLOSE FIREFOX BEFORE RUNNING THIS SCRIPT


def split_string_evenly(text: str, max_per_group: int = 100) -> list[list[str]]:
    # Step 1: Split the string into lines
    lines = text.splitlines()

    n = len(lines)
    if n == 0:
        return []

    # Step 2: Determine number of groups
    num_groups = -(-n // max_per_group)  # ceiling division

    # Step 3: Evenly divide lines into roughly equal-sized groups
    base_size = n // num_groups
    remainder = n % num_groups

    groups: list[list[str]] = []
    start = 0
    for i in range(num_groups):
        # Distribute remainder (the first 'remainder' groups get +1 item)
        size = base_size + (1 if i < remainder else 0)
        groups.append(lines[start : start + size])
        start += size

    return groups


ALLOWED_LANGS: Final[tuple[str, ...]] = tuple(
    sorted({"Any", "en", "jp", "zh-CN", "zh-TW", "ft", "de", "it", "kr", "pt", "ru", "es"})
)


def parse_language_thresholds(arg_value: str) -> dict[str, int]:
    """Parse and validate a language:threshold list.

    Example: 'en:0,es:25,pt:50,it:50'.
    'en:0,es:25,pt:50,it:50'.

    Validation rules:
    - If not provided, default is {"Any": 0}
    - The first language must have threshold == 0
    - Thresholds must be integers >= 1, except for the first one
    - No repeated languages
    - "Any" can only appear as the last language
    """
    if not arg_value:
        return {"Any": 0}

    pairs = [p.strip() for p in arg_value.split(",") if p.strip()]
    if not pairs:
        msg = "Can't be empty."
        raise argparse.ArgumentTypeError(msg)

    thresholds: dict[str, int] = {}
    for index, pair in enumerate(pairs):
        language, threshold = _parse_language_threshold_pair(pair, index)
        if language not in ALLOWED_LANGS:
            msg = f"Language '{language}' is not allowed. Allowed: {ALLOWED_LANGS}."
            raise argparse.ArgumentTypeError(msg)
        if language in thresholds:
            msg = f"Duplicate language '{language}' found."
            raise argparse.ArgumentTypeError(msg)
        if language == "Any" and index != len(pairs) - 1:
            msg = "'Any' language may only appear as the last entry."
            raise argparse.ArgumentTypeError(msg)
        thresholds[language] = threshold
    return thresholds


def _parse_language_threshold_pair(pair: str, index: int) -> tuple[str, int]:
    """Parse one language threshold pair and validate its numeric value."""
    if ":" not in pair:
        msg = f"Invalid format for language:threshold '{pair}'. Expected 'lang:int'."
        raise argparse.ArgumentTypeError(msg)
    language, threshold_text = (part.strip() for part in pair.split(":", 1))
    if not threshold_text.isdigit():
        msg = f"Threshold for language '{language}' must be an integer (got '{threshold_text}')."
        raise argparse.ArgumentTypeError(msg)
    threshold = int(threshold_text)
    if index == 0 and threshold != 0:
        msg = f"The first language ('{language}') must have a threshold of 0."
        raise argparse.ArgumentTypeError(msg)
    if index > 0 and threshold < 1:
        msg = f"Language '{language}' must have a positive threshold (>=1)."
        raise argparse.ArgumentTypeError(msg)
    return language, threshold


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--card-list", "-c", required=True, help="Path to a text file containing the card list (required)."
    )

    parser.add_argument("--expansion-choice", "-e", default="Any", help="Expansion filter (default: Any).")

    parser.add_argument(
        "--foil-choice", "-f", choices=["Any", "Yes", "No"], default="Any", help="Foil filter (default: Any)."
    )

    parser.add_argument(
        "--condition",
        "-n",
        choices=["Any", "Near Mint", "Slightly Played", "Moderately Played", "Played", "Poor"],
        default="Any",
        help="Card condition filter (default: Any).",
    )

    parser.add_argument(
        "--language-price-thresholds",
        "-l",
        type=parse_language_thresholds,
        default={"Any": 0},
        help=(
            "Language thresholds in cents. Format: 'en:0,es:25,pt:50'. First must be 0; 'Any' is last. "
            f"Allowed languages: {{{','.join(lang for lang in ALLOWED_LANGS)}}}. "
            "(default: 'Any:0')"
        ),
    )

    parser.add_argument(
        "--browser-profile",
        "-b",
        help="Path to Firefox profile. E.g. "
        r"C:\Users\<user>\AppData\Roaming\Firefox\Profiles\<random_string>.default-release",
    )

    return parser.parse_args()


args = parse_args()


options = Options()
if args.browser_profile:
    options.add_argument("-profile")
    options.add_argument(args.browser_profile)
driver = webdriver.Firefox(options=options)

# --- Step 0: Click the "Accept" (cookies) button ---
driver.get("https://www.cardtrader.com/wishlists/new")

try:
    accept_button = WebDriverWait(driver, 2).until(
        expected_conditions.element_to_be_clickable((By.XPATH, "//button[normalize-space(text())='Accept']"))
    )
    accept_button.click()
except OSError, RuntimeError, ValueError:
    pass

# --- Step 1: Click the "Match card printing" checkbox ---
checkbox = WebDriverWait(driver, 10).until(
    expected_conditions.element_to_be_clickable((By.ID, "only-identical-copies-checkbox"))
)
checkbox.click()

with Path(args.card_list).open("r", encoding="utf-8") as card_list_file:
    card_list_text = card_list_file.read()
for chunck in split_string_evenly(card_list_text):
    # --- Step 2: Click the "Paste text" button ---
    paste_button = WebDriverWait(driver, 10).until(
        expected_conditions.element_to_be_clickable(
            (By.XPATH, "//button[contains(@class, 'btn') and normalize-space(text())='Paste text']")
        )
    )
    paste_button.click()

    # --- Step 3: Wait for textarea and paste card list ---
    textarea = WebDriverWait(driver, 10).until(
        expected_conditions.presence_of_element_located((By.XPATH, "//textarea[@type='text']"))
    )
    textarea.clear()
    textarea.send_keys("\n".join(chunck))

    # --- Step 4: Click the "Analyze text" button ---
    analyze_button = WebDriverWait(driver, 10).until(
        expected_conditions.element_to_be_clickable(
            (
                By.XPATH,
                "//button[contains(@class, 'btn') and normalize-space(text())='Analyze text']",
            )
        )
    )
    analyze_button.click()

    # --- Step 5: Wait for the result message ---
    message_div = WebDriverWait(driver, 10).until(
        expected_conditions.presence_of_element_located(
            (
                By.XPATH,
                "//div[contains(text(), 'will be imported') and contains(., 'will be ignored')]",
            )
        )
    )
    message_text = str(message_div.get_attribute("innerHTML"))
    match = re.search(
        r"(\d+) cards? will be imported.*(\d+) lines? will be ignored",
        message_text,
        flags=re.DOTALL,
    )
    if match:
        cards_imported = int(match.group(1))
        lines_ignored = int(match.group(2))
        if lines_ignored > 0:
            print(f"Warning: {lines_ignored} card names were ignored.")
        else:
            print(f"{cards_imported} card names were be imported.")
    else:
        msg = f"Couldn't find how many cards were correctly imported. {message_text=}"
        raise RuntimeError(msg)

    # --- Step 6: Click the "Import..." button ---
    import_button = WebDriverWait(driver, 10).until(
        expected_conditions.element_to_be_clickable(
            (
                By.XPATH,
                "//button[contains(@class, 'btn') and starts-with(normalize-space(text()), 'Import')]",
            )
        )
    )
    import_button.click()


# --- Step 7: Select the appropriate settings for each card ---
# --- Expansion dropdowns ---


def _set_expansion(expn: str = "Any") -> None:
    if expn == "Any":
        expn = ""
    expansion_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="expansion"]')
    for sel_elem in expansion_selects:
        select = Select(sel_elem)
        if select.first_selected_option.get_attribute("value") != expn:
            driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", sel_elem)
            with suppress(OSError, RuntimeError, ValueError):
                select.select_by_value(expn)


# --- Language dropdowns ---
def _set_language(lang: str = "Any") -> None:
    if lang == "Any":
        lang = ""
    language_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="language"]')
    for sel_elem in language_selects:
        select = Select(sel_elem)
        if select.first_selected_option.get_attribute("value") != lang:
            driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", sel_elem)
            try:
                select.select_by_value(lang)
            except OSError, RuntimeError, ValueError:
                print(f"Warning: Couldn't select language '{lang}'.")


# --- Condition dropdowns ---
def _set_condition(cond: str = "Any") -> None:
    if cond == "Any":
        cond = ""
    condition_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="condition"]')
    for sel_elem in condition_selects:
        select = Select(sel_elem)
        if select.first_selected_option.get_attribute("value") != cond:
            driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", sel_elem)
            try:
                select.select_by_value(cond)
            except OSError, RuntimeError, ValueError:
                print(f"Warning: Couldn't select condition '{cond}'.")


# --- Foil dropdowns ---
def _set_foil(foil: str = "Any") -> None:
    if foil == "Any":
        foil = ""
    condition_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="foil"]')
    for sel_elem in condition_selects:
        select = Select(sel_elem)
        if select.first_selected_option.get_attribute("value") != foil:
            driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", sel_elem)
            with suppress(OSError, RuntimeError, ValueError):
                select.select_by_value(foil)


def check_select_all(driver: WebDriver, *, select: bool = True, timeout: int = 10) -> None:
    """Check the 'check_all' checkbox if it isn't already checked."""
    header = WebDriverWait(driver, 10).until(
        expected_conditions.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
    )
    wait = WebDriverWait(header, timeout)

    # Wait for checkbox to be present and interactable
    checkbox = wait.until(expected_conditions.element_to_be_clickable((By.NAME, "check_all")))
    driver.execute_script("window.scrollTo(0, 0);")

    if (not checkbox.is_selected() and select) or (checkbox.is_selected() and not select):
        checkbox.click()
    time.sleep(0.5)


def set_expansion(option_text: str, timeout: int = 10) -> None:
    """Select an Expansion option like '(RVR) Ravnica Remastered'."""
    check_select_all(driver)
    header = WebDriverWait(driver, 10).until(
        expected_conditions.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
    )
    wait = WebDriverWait(header, timeout)
    # Click the dropdown button
    expansion_button = wait.until(expected_conditions.element_to_be_clickable((By.ID, "setExpansionButton")))
    driver.execute_script("window.scrollTo(0, 0);")
    expansion_button.click()

    # Wait for dropdown menu and select item
    option = wait.until(
        expected_conditions.element_to_be_clickable(
            (
                By.XPATH,
                f"//div[@aria-labelledby='setExpansionButton']//a[normalize-space()='{option_text}']",
            )
        )
    )
    option.click()
    time.sleep(0.25)
    check_select_all(driver, select=False)
    time.sleep(0.25)
    _set_expansion(option_text)


def set_language(option_text: str, timeout: int = 10) -> None:
    """Select a Language option like 'EN', 'FR', or 'Any'."""
    check_select_all(driver)
    option_text_upper = option_text.upper() if option_text != "Any" else option_text
    header = WebDriverWait(driver, 10).until(
        expected_conditions.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
    )
    wait = WebDriverWait(header, timeout)
    language_button = wait.until(expected_conditions.element_to_be_clickable((By.ID, "setLanguageButton")))
    driver.execute_script("window.scrollTo(0, 0);")
    language_button.click()

    option = wait.until(
        expected_conditions.element_to_be_clickable(
            (
                By.XPATH,
                f"//div[@aria-labelledby='setLanguageButton']//a[normalize-space()='{option_text_upper}']",
            )
        )
    )
    option.click()
    time.sleep(0.25)
    check_select_all(driver, select=False)
    time.sleep(0.25)
    _set_language(option_text)


def set_condition(option_text: str, timeout: int = 10) -> None:
    """Select a Condition option like 'Near Mint' or 'Played'."""
    check_select_all(driver)
    header = WebDriverWait(driver, 10).until(
        expected_conditions.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
    )
    wait = WebDriverWait(header, timeout)
    condition_button = wait.until(expected_conditions.element_to_be_clickable((By.ID, "setConditionButton")))
    driver.execute_script("window.scrollTo(0, 0);")
    condition_button.click()

    option = wait.until(
        expected_conditions.element_to_be_clickable(
            (
                By.XPATH,
                f"//div[@aria-labelledby='setConditionButton']//a[normalize-space()='{option_text}']",
            )
        )
    )
    option.click()
    time.sleep(0.25)
    check_select_all(driver, select=False)
    time.sleep(0.25)
    _set_condition(option_text)


def set_foil(option_text: str, timeout: int = 10) -> None:
    """Select a Foil option like 'true', 'false', or 'Any'."""
    check_select_all(driver)
    header = WebDriverWait(driver, 10).until(
        expected_conditions.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
    )
    wait = WebDriverWait(header, timeout)
    foil_button = wait.until(expected_conditions.element_to_be_clickable((By.ID, "setFoilButton")))
    driver.execute_script("window.scrollTo(0, 0);")
    foil_button.click()

    option = wait.until(
        expected_conditions.element_to_be_clickable(
            (
                By.XPATH,
                f"//div[@aria-labelledby='setFoilButton']//a[normalize-space()='{option_text}']",
            )
        )
    )
    option.click()
    time.sleep(0.25)
    check_select_all(driver, select=False)
    time.sleep(0.25)
    _set_foil(option_text)


# --- Step 8: Click the "Optimize"/"Refresh" button ---
def click_button(button_name: str) -> None:
    optimize_button = WebDriverWait(driver, 10).until(
        expected_conditions.element_to_be_clickable(
            (
                By.XPATH,
                f"//button[contains(@class, 'btn') and contains(normalize-space(.), {button_name})]",
            )
        )
    )
    driver.execute_script("window.scrollTo(0, 0);")
    optimize_button.click()


# --- Step 9: Wait until the optimizer is done ---
def wait_for_optimizer() -> None:
    container = WebDriverWait(driver, 10).until(
        expected_conditions.presence_of_element_located(
            (
                By.XPATH,
                "//div[h5[contains(text(), 'CardTrader Zero')] and descendant::a[normalize-space(text())='Buy now']]",
            )
        )
    )
    buy_now_link = container.find_element(By.XPATH, ".//a[normalize-space(text())='Buy now']")
    WebDriverWait(driver, 300).until(lambda _: buy_now_link.get_attribute("disabled") is None)
    driver.execute_script("window.scrollTo(0, 0);")
    actions = ActionChains(driver)
    actions.move_to_element(buy_now_link).perform()
    time.sleep(0.5)


# --- Step 10: Get the prices ---
def get_prices() -> dict[str, int]:
    cards: dict[str, int] = {}
    # Find all card rows that have class 'deck-table-row' and attributes data-id and data-uuid
    card_rows = driver.find_elements(
        By.XPATH,
        "//div[contains(@class, 'deck-table-row') and @data-id and @data-uuid]",
    )
    for row in card_rows:
        # Get quantity
        name_span = row.find_element(By.CSS_SELECTOR, "div.deck-table-row__quantity > input")
        quantity = int(
            str(name_span.get_attribute("value"))
        )  # TODO: Validate it's correct, sometimes there's not enough stock.
        # Get card name
        name_span = row.find_element(By.CSS_SELECTOR, "div.deck-table-row__name > span")
        card_name = name_span.text.strip()
        # Get price text from nested div.col.text-right
        price_div = row.find_element(By.CSS_SELECTOR, "div.deck-table-row__price > div > div.col.text-right")
        price_text = price_div.text.strip()  # e.g. "€1.10"
        # Remove euro sign and whitespace, convert to float, then to cents int
        price_value = price_text.replace("€", "").replace("\xa0", "").strip()
        try:
            price_float = float(price_value)
        except ValueError:
            print(f"Warning: Couldn't get price for card {card_name!r}.")
            continue
        price_cents = round(price_float * 100)
        # Save card and price
        cards[card_name] = price_cents // quantity
    return cards


def get_prices2() -> dict[str, int]:
    cards: dict[str, int] = {}

    rows = driver.find_elements(By.CSS_SELECTOR, ".deck-table-row[data-id][data-uuid]")

    for row in rows:
        # quantity
        try:
            quantity_value = row.find_element(By.CSS_SELECTOR, ".deck-table-row__quantity input").get_attribute("value")
            quantity = int(quantity_value or 0)
        except ValueError:
            quantity = 0
        if quantity <= 0:
            continue

        # name
        card_name = row.find_element(By.CSS_SELECTOR, ".deck-table-row__name span").text.strip()

        # price
        price_text = row.find_element(By.CSS_SELECTOR, ".deck-table-row__price .text-right").text.strip()
        price_value = price_text.replace("€", "").replace("\xa0", "").replace(",", ".").strip()

        try:
            price_cents = round(float(price_value) * 100)
        except ValueError:
            print(f"Warning: Couldn't get price for card {card_name!r}.")
            continue

        cards[card_name] = price_cents // quantity

    return cards


# --- Step 11: Get the prices in all languages ---

cards: dict[str, dict[str, int]] = {}
time.sleep(1)
for idx, language in enumerate(args.language_price_thresholds):
    set_expansion(args.expansion_choice)
    set_language(language)
    set_condition(args.condition)
    set_foil(args.foil_choice)
    click_button("'Optimize'" if idx == 0 else "'Refresh'")
    wait_for_optimizer()
    cards[language] = get_prices2()
    print(f"cards[{language}]={cards[language]}")
with Path("card_prices_by_lang.json").open("w", encoding="utf-8") as output_file:
    json.dump(cards, output_file, indent=2, sort_keys=True)

# If only one language, no need to choose language per card and optimize.
if len(args.language_price_thresholds) == 1:
    sys.exit()


# --- Step 12: Choose language by card ---
def choose_languages1(prices_by_lang: dict[str, dict[str, int]], config: dict[str, int]) -> dict[str, str]:
    # Calculate the price diff for the language and the currently selected language.
    # If the price diff is >= price diff threshold, choose that language.
    chosen_languages: dict[str, str] = {}

    all_cards: set[str] = set()
    for lang_prices in prices_by_lang.values():
        all_cards.update(lang_prices.keys())

    for card in all_cards:
        sel_lang = None
        sel_price = None
        for lang, threshold in config.items():
            price = prices_by_lang.get(lang, {}).get(card)
            if price is None:
                continue
            if sel_lang is None or sel_price is None:
                sel_lang = lang
                sel_price = price
                continue
            price_diff = sel_price - price
            if price_diff >= threshold:
                sel_lang = lang
                sel_price = price
        if sel_lang is not None:
            chosen_languages[card] = sel_lang

    return chosen_languages


def choose_languages2(prices_by_lang: dict[str, dict[str, int]], config: dict[str, int]) -> dict[str, str]:
    # Calculate the price diff for the language and the base language (first in config).
    # If the price diff is >= price diff threshold and the price is < the currently selected price,
    # choose that language.
    chosen_languages = {}

    base_lang = next(iter(config.keys()))
    base_prices = prices_by_lang.get(base_lang, {})
    all_cards = set()
    for lang_prices in prices_by_lang.values():
        all_cards.update(lang_prices.keys())

    for card in all_cards:
        sel_lang = base_lang
        sel_price = base_prices.get(card, 1000000000)
        for lang, threshold in list(config.items())[1:]:
            price = prices_by_lang.get(lang, {}).get(card)
            if price is None:
                continue
            price_diff = base_prices.get(card, 1000000000) - price
            if price_diff >= threshold and price < sel_price:
                sel_lang = lang
                sel_price = price
        chosen_languages[card] = sel_lang

    return chosen_languages


def choose_languages3(prices_by_lang: dict[str, dict[str, int]], config: dict[str, int]) -> dict[str, str]:
    # Calculate the price diff (1) for the language and the currently selected language.
    # Calculate the price diff (2) for the language and the base language (first in config).
    # If the price diff 1 is >= price diff threshold and the price diff 2 is >= accumulated price diff threshold,
    # chose that language.
    chosen_languages = {}

    base_lang = next(iter(config.keys()))
    base_prices = prices_by_lang.get(base_lang, {})
    all_cards = set()
    for lang_prices in prices_by_lang.values():
        all_cards.update(lang_prices.keys())

    for card in all_cards:
        sel_lang = None
        sel_price = None
        accumulated_threshold = 0
        for lang, threshold in config.items():
            accumulated_threshold += threshold
            price = prices_by_lang.get(lang, {}).get(card)
            if price is None:
                continue
            if sel_lang is None or sel_price is None:
                sel_lang = lang
                sel_price = price
                continue
            price_diff_1 = sel_price - price
            price_diff_2 = base_prices.get(card, 1000000000) - price
            base_price = base_prices.get(card, 1000000000)
            print(f"[DEBUG] {card=} {sel_lang=} {lang=} {sel_price=} {price=} {base_price=} ")
            if price_diff_1 >= threshold and price_diff_2 >= accumulated_threshold:
                print(f"[DEBUG] Choosing language {lang!r}")
                sel_lang = lang
                sel_price = price
            else:
                print(f"[DEBUG] Not choosing language {lang!r}")
        if sel_lang is not None:
            chosen_languages[card] = sel_lang
        print()
    return chosen_languages


cards_chosen_lang = choose_languages3(cards, args.language_price_thresholds)
cards_by_lang: dict[str, list[str]] = {}
for key, value in cards_chosen_lang.items():
    cards_by_lang.setdefault(value, []).append(key)
print(f"{cards_chosen_lang=}")
with Path("chosen_languages.json").open("w", encoding="utf-8") as output_file:
    json.dump(cards_chosen_lang, output_file, indent=2, sort_keys=True)

for language in args.language_price_thresholds:
    print(f"Total in {language}    ({len(cards[language])} cards): {sum(cards[language].values())}")


# --- Step 13: Optimize cards using the chosen language ---
set_expansion(args.expansion_choice)
set_language(next(iter(args.language_price_thresholds.keys())))  # Set to first language as placeholder
# Find all card rows with required attributes (same as before)
card_rows = driver.find_elements(By.XPATH, "//div[contains(@class, 'deck-table-row') and @data-id and @data-uuid]")
for row in card_rows:
    # Get card name
    name_span = row.find_element(By.CSS_SELECTOR, ".deck-table-row__name span")
    card_name = name_span.text.strip()
    # Get chosen language for this card
    chosen_lang = cards_chosen_lang.get(card_name)
    if not chosen_lang:
        print(
            f"Error: Couldn't find the chosen language for card {card_name!r}. "
            f"Choosing {next(iter(args.language_price_thresholds.keys()))} as fallback."
        )
        chosen_lang = next(iter(args.language_price_thresholds.keys()))
    # Find the language dropdown in this row
    select_element = row.find_element(By.CSS_SELECTOR, 'select[name="language"]')
    select = Select(select_element)
    # Change language if different from current value
    if str(select.first_selected_option.get_attribute("value")).lower() != chosen_lang.lower():
        try:
            driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", select_element)
            select.select_by_value(chosen_lang if chosen_lang != "Any" else "")
        except OSError, RuntimeError, ValueError:
            print(
                f"Error: Couldn't select the chosen language for card {card_name!r}. "
                f"Selected {next(iter(args.language_price_thresholds.keys()))} as fallback."
            )

set_condition(args.condition)
set_foil(args.foil_choice)
click_button("'Refresh'")
wait_for_optimizer()
cards_optimized = get_prices2()
print(f"{cards_optimized=}")
print(f"Total optimized by language: {sum(cards_optimized.values())}")
with Path("final_card_prices.json").open("w", encoding="utf-8") as output_file:
    json.dump(cards_optimized, output_file, indent=2, sort_keys=True)
