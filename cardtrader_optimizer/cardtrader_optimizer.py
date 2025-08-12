import re

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

card_list = """\
Phyrexian Arena
Lifegift
Social Climber
Nexus of Fate
Polluted Bonds
Pongify
Campfire
Deathrite Shaman
Shifting Woodland
Enduring Curiosity
Mockingbird
Unholy Annex // Ritual Chamber
The Indomitable
Toski, Bearer of Secrets
Scute Swarm
Wound Reflection
Case of the Locked Hothouse
Loot, Exuberant Explorer
Tamiyo's Safekeeping
Arcane Denial
Entish Restoration
Wayward Swordtooth
Propaganda
Ancient Cornucopia
Zulaport Cutthroat
Wizard Class
"""


driver = webdriver.Firefox()
driver.get("https://www.cardtrader.com/wishlists/new")

# --- Step 0: Click the "Accept" button ---
accept_button = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(text())='Accept']"))
)
accept_button.click()

# --- Step 1: Click the "Paste text" button ---
paste_button = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn') and normalize-space(text())='Paste text']"))
)
paste_button.click()

# --- Step 2: Wait for textarea and paste card list ---
textarea = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//textarea[@type='text']")))
textarea.clear()
textarea.send_keys(card_list)

# --- Step 3: Click the "Analyze text" button ---
analyze_button = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable(
        (By.XPATH, "//button[contains(@class, 'btn') and normalize-space(text())='Analyze text']")
    )
)
analyze_button.click()

# --- Step 4: Wait for the result message ---
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

# --- Step 5: Click the "Import..." button ---
import_button = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable(
        (By.XPATH, "//button[contains(@class, 'btn') and starts-with(normalize-space(text()), 'Import')]")
    )
)
import_button.click()

# --- Step 6: Click the "Match card printing" checkbox ---
checkbox = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "only-identical-copies-checkbox")))
checkbox.click()


# --- Step 7: Select the appropriate settings for each card ---
# --- Expansion dropdowns ---
def set_expansion(expn="Any"):
    if expn == "Any":
        expn = ""
    expansion_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="expansion"]')
    for sel_elem in expansion_selects:
        select = Select(sel_elem)
        # if select.first_selected_option.get_attribute("value") != expn:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sel_elem)
        try:
            select.select_by_value(expn)
        except Exception:
            # print(f"Warning: Couldn't select expansion '{expn}'.")
            pass


set_expansion("Any")


# --- Language dropdowns ---
def set_language(lang="en"):
    language_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="language"]')
    for sel_elem in language_selects:
        select = Select(sel_elem)
        if select.first_selected_option.get_attribute("value") != lang:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sel_elem)
            try:
                select.select_by_value(lang)
            except Exception:
                print(f"Warning: Couldn't select language '{lang}'.")


set_language("en")


# --- Condition dropdowns ---
def set_condition(cond="Played"):
    condition_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="condition"]')
    for sel_elem in condition_selects:
        select = Select(sel_elem)
        if select.first_selected_option.get_attribute("value") != cond:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sel_elem)
            try:
                select.select_by_value(cond)
            except Exception:
                print(f"Warning: Couldn't select condition '{cond}'.")


set_condition("Played")


# --- Foil dropdowns ---
def set_foil(foil=""):
    if foil == "Any":
        foil = ""
    condition_selects = driver.find_elements(By.CSS_SELECTOR, 'select[name="foil"]')
    for sel_elem in condition_selects:
        select = Select(sel_elem)
        if select.first_selected_option.get_attribute("value") != foil:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sel_elem)
            try:
                select.select_by_value(foil)
            except Exception:
                # print(f"Warning: Couldn't select foil '{foil}'.")
                pass


set_foil("Any")


# --- Step 8: Click the "Optimize" button ---
optimize_button = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable(
        (By.XPATH, "//button[contains(@class, 'btn') and contains(normalize-space(.), 'Optimize')]")
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
    actions = ActionChains(driver)
    actions.move_to_element(buy_now_link).perform()


wait_for_optimizer()


# --- Step 10: Get the prices ---
def get_prices():
    cards = {}
    # Find all card rows that have class 'deck-table-row' and attributes data-id and data-uuid
    card_rows = driver.find_elements(By.XPATH, "//div[contains(@class, 'deck-table-row') and @data-id and @data-uuid]")
    for row in card_rows:
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
        cards[card_name] = price_cents
    return cards


cards = {}
cards["en"] = get_prices()
print(f"{cards['en']=}")


# --- Step 11: Get the prices in other languages ---
def click_refresh_button():
    optimize_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(@class, 'btn') and contains(normalize-space(.), 'Refresh')]")
        )
    )
    driver.execute_script("window.scrollTo(0, 0);")
    optimize_button.click()


set_expansion("Any")
set_language("es")
set_condition("Played")
set_foil("Any")
click_refresh_button()
wait_for_optimizer()
cards["es"] = get_prices()
print(f"{cards['es']=}")

set_expansion("Any")
set_language("pt")
set_condition("Played")
set_foil("Any")
click_refresh_button()
wait_for_optimizer()
cards["pt"] = get_prices()
print(f"{cards['pt']=}")

set_expansion("Any")
set_language("it")
set_condition("Played")
set_foil("Any")
click_refresh_button()
wait_for_optimizer()
cards["it"] = get_prices()
print(f"{cards['it']=}")


# --- Step 12: Choose language by card ---
lang_config = {"en": 0, "es": 25, "pt": 25, "it": 25}


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


cards_chosen_lang = choose_languages(cards, lang_config)
print(f"{cards_chosen_lang=}")

print(f"Total in English    ({len(cards['en'])} cards): {sum(cards['en'].values())}")
print(f"Total in Spanish    ({len(cards['es'])} cards): {sum(cards['es'].values())}")
print(f"Total in Portuguese ({len(cards['pt'])} cards): {sum(cards['pt'].values())}")
print(f"Total in Italian    ({len(cards['it'])} cards): {sum(cards['it'].values())}")

# --- Step 13: Optimize cards using the chosen language ---
set_expansion("Any")
# Find all card rows with required attributes (same as before)
card_rows = driver.find_elements(By.XPATH, "//div[contains(@class, 'deck-table-row') and @data-id and @data-uuid]")
for row in card_rows:
    # Get card name
    name_span = row.find_element(By.CSS_SELECTOR, "div.deck-table-row__name > span")
    card_name = name_span.text.strip()
    # Get chosen language for this card
    chosen_lang = cards_chosen_lang.get(card_name)
    if not chosen_lang:
        print(f"Error: Couldn't find the chosen language for card {repr(card_name)}. Choosing EN as fallback.")
        chosen_lang = "en"
    # Find the language dropdown in this row
    lang_select_element = row.find_element(By.CSS_SELECTOR, 'select[name="language"]')
    select = Select(lang_select_element)
    # Change language if different from current value
    if select.first_selected_option.get_attribute("value") != chosen_lang:
        try:
            select.select_by_value(chosen_lang)
        except Exception:
            print(f"Error: Couldn't select the chosen language for card {repr(card_name)}. Selecting Any as fallback.")
set_condition("Played")
set_foil("Any")
click_refresh_button()
wait_for_optimizer()
cards_optimized = get_prices()
print(f"{cards_optimized=}")
print(f"Total optimized by language: {sum(cards_optimized.values())}")
