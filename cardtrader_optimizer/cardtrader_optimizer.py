import argparse
import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

# CLOSE FIREFOX BEFORE RUNNING THIS SCRIPT

"""
Steps to Locate Your Firefox Profile Folder:
1. Open Firefox.
2. In the address bar, type: about:profiles and press Enter.
3. You'll see a list of profiles. Look for the one labeled "Default" or the one you actively use.
4. Under that profile, find the "Root Directory" path.
"""


def split_string_evenly(text: str, max_per_group=100) -> list[list[str]]:
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


ALLOWED_LANGS = sorted({"Any", "en", "jp", "zh-CN", "zh-TW", "ft", "de", "it", "kr", "pt", "ru", "es"})


def parse_language_deltas(arg_value: str) -> dict[str, int]:
    """
    Parse and validate a language:delta list such as:
    'en:0,es:25,pt:50,it:50'

    Validation rules:
    - If not provided, default is {"Any": 0}
    - The first language must have delta == 0
    - Deltas must be integers >= 1, except for the first one
    - No repeated languages
    - "Any" can only appear as the last language
    """
    if not arg_value:
        return {"Any": 0}

    pairs = [p.strip() for p in arg_value.split(",") if p.strip()]
    lang_delta = {}

    for i, pair in enumerate(pairs):
        if ":" not in pair:
            raise argparse.ArgumentTypeError(f"Invalid format for language:delta '{pair}'. Expected 'lang:int'.")

        lang, delta_str = pair.split(":", 1)

        delta_str = delta_str.strip()
        # Validate delta is integer
        if not delta_str.isdigit():
            raise argparse.ArgumentTypeError(f"Delta for language '{lang}' must be an integer (got '{delta_str}').")
        delta = int(delta_str)
        # Validate delta value for first element
        if i == 0 and delta != 0:
            raise argparse.ArgumentTypeError(f"The first language ('{lang}') must have a delta of 0.")
        # Validate delta value for non-first elements
        if i > 0 and delta < 1:
            raise argparse.ArgumentTypeError(f"Language '{lang}' must have a positive delta (>=1).")

        lang = lang.strip()
        # Validate if allowed lang
        if lang not in ALLOWED_LANGS:
            raise argparse.ArgumentTypeError(f"Language '{lang}' is not allowed. Allowed: {ALLOWED_LANGS}.")
        # Validate lang duplicates
        if lang in lang_delta:
            raise argparse.ArgumentTypeError(f"Duplicate language '{lang}' found.")
        # "Any" only allowed as last lang
        if lang == "Any" and i != len(pairs) - 1:
            raise argparse.ArgumentTypeError("'Any' language may only appear as the last entry.")

        lang_delta[lang] = delta

    if not lang_delta:
        raise argparse.ArgumentTypeError("Can't be empty.")

    return lang_delta


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--card-list", "-c", required=True, help="Path to a text file containing the card list (required)."
    )

    parser.add_argument("--expansion-choice", "-e", default="Any", help="Expansion filter (default: Any).")

    parser.add_argument(
        "--foil-choice",
        "-f",
        choices=["Any", "Yes", "No"],
        default="Any",
        help="Foil filter (default: Any).",
    )

    parser.add_argument(
        "--condition",
        "-n",
        choices=["Any", "Near Mint", "Slightly Played", "Moderately Played", "Played", "Poor"],
        default="Any",
        help="Card condition filter (default: Any).",
    )

    parser.add_argument(
        "--language-price-deltas",
        "-l",
        type=parse_language_deltas,
        default={"Any": 0},
        help=(
            "Language price deltas in cents. Format example: 'en:0,es:25,pt:50'. First must be 0, 'Any' only allowed last. "
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

    args = parser.parse_args()

    return args


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
        EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(text())='Accept']"))
    )
    accept_button.click()
except Exception:
    pass

# --- Step 1: Click the "Match card printing" checkbox ---
checkbox = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "only-identical-copies-checkbox")))
checkbox.click()

for chunck in split_string_evenly(Path(args.card_list).open().read()):
    # --- Step 2: Click the "Paste text" button ---
    paste_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(@class, 'btn') and normalize-space(text())='Paste text']")
        )
    )
    paste_button.click()

    # --- Step 3: Wait for textarea and paste card list ---
    textarea = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//textarea[@type='text']")))
    textarea.clear()
    textarea.send_keys("\n".join(chunck))

    # --- Step 4: Click the "Analyze text" button ---
    analyze_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(@class, 'btn') and normalize-space(text())='Analyze text']")
        )
    )
    analyze_button.click()

    # --- Step 5: Wait for the result message ---
    message_div = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[contains(text(), 'will be imported') and contains(., 'will be ignored')]")
        )
    )
    message_text = str(message_div.get_attribute("innerHTML"))
    match = re.search(r"(\d+) cards? will be imported.*(\d+) lines? will be ignored", message_text, flags=re.DOTALL)
    if match:
        cards_imported = int(match.group(1))
        lines_ignored = int(match.group(2))
        if lines_ignored > 0:
            print(f"Warning: {lines_ignored} card names were ignored.")
        else:
            print(f"{cards_imported} card names were be imported.")
    else:
        raise RuntimeError(f"Couldn't find how many cards were correctly imported. {message_text=}")

    # --- Step 6: Click the "Import..." button ---
    import_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(@class, 'btn') and starts-with(normalize-space(text()), 'Import')]")
        )
    )
    import_button.click()


# --- Step 7: Select the appropriate settings for each card ---
# --- Expansion dropdowns ---


def _set_expansion(expn="Any"):
    if expn == "Any":
        expn = ""
    expansion_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="expansion"]')
    for sel_elem in expansion_selects:
        select = Select(sel_elem)
        if select.first_selected_option.get_attribute("value") != expn:
            driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", sel_elem)
            try:
                select.select_by_value(expn)
            except Exception:
                # print(f"Warning: Couldn't select expansion '{expn}'.")
                pass


# --- Language dropdowns ---
def _set_language(lang="Any"):
    if lang == "Any":
        lang = ""
    language_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="language"]')
    for sel_elem in language_selects:
        select = Select(sel_elem)
        if select.first_selected_option.get_attribute("value") != lang:
            driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", sel_elem)
            try:
                select.select_by_value(lang)
            except Exception:
                print(f"Warning: Couldn't select language '{lang}'.")


# --- Condition dropdowns ---
def _set_condition(cond="Any"):
    if cond == "Any":
        cond = ""
    condition_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="condition"]')
    for sel_elem in condition_selects:
        select = Select(sel_elem)
        if select.first_selected_option.get_attribute("value") != cond:
            driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", sel_elem)
            try:
                select.select_by_value(cond)
            except Exception:
                print(f"Warning: Couldn't select condition '{cond}'.")


# --- Foil dropdowns ---
def _set_foil(foil="Any"):
    if foil == "Any":
        foil = ""
    condition_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="foil"]')
    for sel_elem in condition_selects:
        select = Select(sel_elem)
        if select.first_selected_option.get_attribute("value") != foil:
            driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", sel_elem)
            try:
                select.select_by_value(foil)
            except Exception:
                # print(f"Warning: Couldn't select foil '{foil}'.")
                pass


def check_select_all(driver, select=True, timeout=10):
    """Check the 'check_all' checkbox if it isn't already checked."""
    header = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
    )
    wait = WebDriverWait(header, timeout)

    # Wait for checkbox to be present and interactable
    checkbox = wait.until(EC.element_to_be_clickable((By.NAME, "check_all")))
    driver.execute_script("window.scrollTo(0, 0);")

    if not checkbox.is_selected() and select:
        checkbox.click()
    elif checkbox.is_selected() and not select:
        checkbox.click()
    time.sleep(0.5)


def set_expansion(option_text, timeout=10):
    """Select an Expansion option like '(RVR) Ravnica Remastered'."""
    check_select_all(driver)
    header = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
    )
    wait = WebDriverWait(header, timeout)
    # Click the dropdown button
    expansion_button = wait.until(EC.element_to_be_clickable((By.ID, "setExpansionButton")))
    driver.execute_script("window.scrollTo(0, 0);")
    expansion_button.click()

    # Wait for dropdown menu and select item
    option = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//div[@aria-labelledby='setExpansionButton']//a[normalize-space()='{option_text}']")
        )
    )
    option.click()
    time.sleep(0.25)
    check_select_all(driver, False)
    time.sleep(0.25)
    _set_expansion(option_text)


def set_language(option_text, timeout=10):
    """Select a Language option like 'EN', 'FR', or 'Any'."""
    check_select_all(driver)
    option_text_upper = option_text.upper() if option_text != "Any" else option_text
    header = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
    )
    wait = WebDriverWait(header, timeout)
    language_button = wait.until(EC.element_to_be_clickable((By.ID, "setLanguageButton")))
    driver.execute_script("window.scrollTo(0, 0);")
    language_button.click()

    option = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//div[@aria-labelledby='setLanguageButton']//a[normalize-space()='{option_text_upper}']")
        )
    )
    option.click()
    time.sleep(0.25)
    check_select_all(driver, False)
    time.sleep(0.25)
    _set_language(option_text)


def set_condition(option_text, timeout=10):
    """Select a Condition option like 'Near Mint' or 'Played'."""
    check_select_all(driver)
    header = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
    )
    wait = WebDriverWait(header, timeout)
    condition_button = wait.until(EC.element_to_be_clickable((By.ID, "setConditionButton")))
    driver.execute_script("window.scrollTo(0, 0);")
    condition_button.click()

    option = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//div[@aria-labelledby='setConditionButton']//a[normalize-space()='{option_text}']")
        )
    )
    option.click()
    time.sleep(0.25)
    check_select_all(driver, False)
    time.sleep(0.25)
    _set_condition(option_text)


def set_foil(option_text, timeout=10):
    """Select a Foil option like 'true', 'false', or 'Any'."""
    check_select_all(driver)
    header = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'deck-table-header')]"))
    )
    wait = WebDriverWait(header, timeout)
    foil_button = wait.until(EC.element_to_be_clickable((By.ID, "setFoilButton")))
    driver.execute_script("window.scrollTo(0, 0);")
    foil_button.click()

    option = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//div[@aria-labelledby='setFoilButton']//a[normalize-space()='{option_text}']")
        )
    )
    option.click()
    time.sleep(0.25)
    check_select_all(driver, False)
    time.sleep(0.25)
    _set_foil(option_text)


# --- Step 8: Click the "Optimize"/"Refresh" button ---
def click_button(button_name):
    optimize_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//button[contains(@class, 'btn') and contains(normalize-space(.), {button_name})]")
        )
    )
    driver.execute_script("window.scrollTo(0, 0);")
    optimize_button.click()


# --- Step 9: Wait until the optimizer is done ---
def wait_for_optimizer():
    container = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
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


# --- Step 10: Get the prices ---
def get_prices():
    cards = {}
    # Find all card rows that have class 'deck-table-row' and attributes data-id and data-uuid
    card_rows = driver.find_elements(By.XPATH, "//div[contains(@class, 'deck-table-row') and @data-id and @data-uuid]")
    for row in card_rows:
        # Get quantity
        name_span = row.find_element(By.CSS_SELECTOR, "div.deck-table-row__quantity > input")
        quantity = int(str(name_span.get_attribute("value")))
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
            print(f"Warning: Couldn't get price for card {repr(card_name)}.")
            continue
        price_cents = int(round(price_float * 100))
        # Save card and price
        cards[card_name] = price_cents // quantity
    return cards


# --- Step 11: Get the prices in all languages ---

cards = {}
time.sleep(1)
for idx, language in enumerate(args.language_price_deltas):
    set_expansion(args.expansion_choice)
    set_language(language)
    set_condition(args.condition)
    set_foil(args.foil_choice)
    click_button("'Optimize'" if idx == 0 else "'Refresh'")
    wait_for_optimizer()
    cards[language] = get_prices()
    print(f"cards[{language}]={cards[language]}")

# If only one language, no need to choose language per card and optimize.
if len(args.language_price_deltas) == 1:
    exit()


# --- Step 12: Choose language by card ---
def choose_languages(prices_by_lang, config):
    chosen_languages = {}
    languages = list(config.keys())

    all_cards = set()
    for lang_prices in prices_by_lang.values():
        all_cards.update(lang_prices.keys())

    for card in all_cards:
        current_lang = None
        current_price = None

        for i, lang in enumerate(languages):
            lang_prices = prices_by_lang.get(lang, {})
            price = lang_prices.get(card)
            if price is None:
                continue

            if current_lang is None:
                current_lang = lang
                current_price = price
            else:
                threshold = config[lang]
                # Compare new price to current price directly
                if (current_price - price) >= threshold:
                    current_lang = lang
                    current_price = price

        if current_lang is not None:
            chosen_languages[card] = current_lang

    return chosen_languages


cards_chosen_lang = choose_languages(cards, args.language_price_deltas)
print(f"{cards_chosen_lang=}")

for language in args.language_price_deltas:
    print(f"Total in {language}    ({len(cards[language])} cards): {sum(cards[language].values())}")


# --- Step 13: Optimize cards using the chosen language ---
set_expansion(args.expansion_choice)
set_language(list(args.language_price_deltas.keys())[0])  # Set to first language as placeholder
# Find all card rows with required attributes (same as before)
card_rows = driver.find_elements(By.XPATH, "//div[contains(@class, 'deck-table-row') and @data-id and @data-uuid]")
for row in card_rows:
    # Get card name
    name_span = row.find_element(By.CSS_SELECTOR, "div.deck-table-row__name > span")
    card_name = name_span.text.strip()
    # Get chosen language for this card
    chosen_lang = cards_chosen_lang.get(card_name)
    if not chosen_lang:
        print(
            f"Error: Couldn't find the chosen language for card {repr(card_name)}. "
            f"Choosing {list(args.language_price_deltas.keys())[0]} as fallback."
        )
        chosen_lang = list(args.language_price_deltas.keys())[0]
    # Find the language dropdown in this row
    select_element = row.find_element(By.CSS_SELECTOR, 'select[name="language"]')
    select = Select(select_element)
    # Change language if different from current value
    if str(select.first_selected_option.get_attribute("value")).lower() != chosen_lang.lower():
        try:
            driver.execute_script("arguments[0].scrollIntoView({'block':'center'});", select_element)
            select.select_by_value(chosen_lang if chosen_lang != "Any" else "")
        except Exception:
            print(
                f"Error: Couldn't select the chosen language for card {repr(card_name)}. "
                f"Selected {list(args.language_price_deltas.keys())[0]} as fallback."
            )

set_condition(args.condition)
set_foil(args.foil_choice)
click_button("'Refresh'")
wait_for_optimizer()
cards_optimized = get_prices()
print(f"{cards_optimized=}")
print(f"Total optimized by language: {sum(cards_optimized.values())}")
