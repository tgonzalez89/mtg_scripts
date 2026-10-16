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
import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from . import policy, pricing

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver

# CLOSE FIREFOX BEFORE RUNNING THIS SCRIPT


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=Path(), help="Directory for price and language JSON outputs."
    )

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
        type=policy.parse_language_thresholds,
        default={"Any": 0},
        help=(
            "Language thresholds in cents. Format: 'en:0,es:25,pt:50'. First must be 0; 'Any' is last. "
            f"Allowed languages: {{{','.join(lang for lang in policy.ALLOWED_LANGS)}}}. "
            "(default: 'Any:0')"
        ),
    )

    parser.add_argument(
        "--browser-profile",
        "-b",
        help="Path to Firefox profile. E.g. "
        r"C:\Users\<user>\AppData\Roaming\Firefox\Profiles\<random_string>.default-release",
    )

    return parser.parse_args(argv)


class CardTraderWorkflow:
    """Own the browser for one CardTrader run and guarantee explicit teardown."""

    def __init__(self, args: argparse.Namespace, driver: WebDriver) -> None:
        self.args = args
        self.driver = driver

    def run(self) -> None:
        _run_with_driver(self.args, self.driver)

    def close(self) -> None:
        self.driver.quit()


def _run(args: argparse.Namespace) -> None:
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options

    args.output_dir.mkdir(parents=True, exist_ok=True)
    options = Options()
    if args.browser_profile:
        options.add_argument("-profile")
        options.add_argument(args.browser_profile)
    workflow = CardTraderWorkflow(args, webdriver.Firefox(options=options))
    try:
        workflow.run()
    finally:
        workflow.close()


def _run_with_driver(args: argparse.Namespace, driver: WebDriver) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import Select, WebDriverWait

    from .page import CardTraderPage

    page = CardTraderPage(driver)

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
    for chunck in policy.split_string_evenly(card_list_text):
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

    # --- Step 7: Apply filters, optimize, and collect prices ---
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
                quantity_value = row.find_element(By.CSS_SELECTOR, ".deck-table-row__quantity input").get_attribute(
                    "value"
                )
                quantity = int(quantity_value or 0)
            except ValueError:
                quantity = 0
            if quantity <= 0:
                continue

            # name
            card_name = row.find_element(By.CSS_SELECTOR, ".deck-table-row__name span").text.strip()

            # price
            try:
                cards[card_name] = pricing.price_per_card_cents(
                    row.find_element(By.CSS_SELECTOR, ".deck-table-row__price .text-right").text,
                    quantity,
                )
            except ValueError:
                print(f"Warning: Couldn't get price for card {card_name!r}.")
                continue

        return cards

    # --- Step 11: Get the prices in all languages ---

    cards: dict[str, dict[str, int]] = {}
    time.sleep(1)
    for idx, language in enumerate(args.language_price_thresholds):
        page.set_expansion(args.expansion_choice)
        page.set_language(language)
        page.set_condition(args.condition)
        page.set_foil(args.foil_choice)
        page.click_button("'Optimize'" if idx == 0 else "'Refresh'")
        page.wait_for_optimizer()
        cards[language] = get_prices2()
        print(f"cards[{language}]={cards[language]}")
    with (args.output_dir / "card_prices_by_lang.json").open("w", encoding="utf-8") as output_file:
        json.dump(cards, output_file, indent=2, sort_keys=True)

    # If only one language, no need to choose language per card and optimize.
    if len(args.language_price_thresholds) == 1:
        return

    # --- Step 12: Choose language by card ---
    cards_chosen_lang = pricing.choose_languages3(cards, args.language_price_thresholds)
    cards_by_lang: dict[str, list[str]] = {}
    for key, value in cards_chosen_lang.items():
        cards_by_lang.setdefault(value, []).append(key)
    print(f"{cards_chosen_lang=}")
    with (args.output_dir / "chosen_languages.json").open("w", encoding="utf-8") as output_file:
        json.dump(cards_chosen_lang, output_file, indent=2, sort_keys=True)

    for language in args.language_price_thresholds:
        print(f"Total in {language}    ({len(cards[language])} cards): {sum(cards[language].values())}")

    # --- Step 13: Optimize cards using the chosen language ---
    page.set_expansion(args.expansion_choice)
    page.set_language(next(iter(args.language_price_thresholds.keys())))  # Set to first language as placeholder
    # Find all card rows with required attributes (same as before)
    card_rows = driver.find_elements(By.XPATH, "//div[contains(@class, 'deck-table-row') and @data-id and @data-uuid]")
    for row in card_rows:
        # Get card name
        name_span = row.find_element(By.CSS_SELECTOR, ".deck-table-row__name span")
        card_name = name_span.text.strip()
        # Get chosen language for this card
        chosen_lang = cards_chosen_lang.get(card_name)
        if not bool(chosen_lang):
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

    page.set_condition(args.condition)
    page.set_foil(args.foil_choice)
    page.click_button("'Refresh'")
    page.wait_for_optimizer()
    cards_optimized = get_prices2()
    print(f"{cards_optimized=}")
    print(f"Total optimized by language: {sum(cards_optimized.values())}")
    with (args.output_dir / "final_card_prices.json").open("w", encoding="utf-8") as output_file:
        json.dump(cards_optimized, output_file, indent=2, sort_keys=True)


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
