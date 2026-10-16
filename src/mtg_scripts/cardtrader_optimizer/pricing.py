"""Pure language-selection decisions from CardTrader price snapshots."""

from __future__ import annotations


def choose_languages1(prices_by_lang: dict[str, dict[str, int]], config: dict[str, int]) -> dict[str, str]:
    chosen_languages: dict[str, str] = {}
    all_cards = {card for prices in prices_by_lang.values() for card in prices}
    for card in all_cards:
        selected_language = None
        selected_price = None
        for language, threshold in config.items():
            price = prices_by_lang.get(language, {}).get(card)
            if price is None:
                continue
            if selected_language is None or selected_price is None:
                selected_language = language
                selected_price = price
                continue
            if selected_price - price >= threshold:
                selected_language = language
                selected_price = price
        if selected_language is not None:
            chosen_languages[card] = selected_language
    return chosen_languages


def choose_languages2(prices_by_lang: dict[str, dict[str, int]], config: dict[str, int]) -> dict[str, str]:
    chosen_languages: dict[str, str] = {}
    base_language = next(iter(config))
    base_prices = prices_by_lang.get(base_language, {})
    all_cards = {card for prices in prices_by_lang.values() for card in prices}
    for card in all_cards:
        selected_language = base_language
        selected_price = base_prices.get(card, 1_000_000_000)
        for language, threshold in list(config.items())[1:]:
            price = prices_by_lang.get(language, {}).get(card)
            if price is None:
                continue
            price_diff = base_prices.get(card, 1_000_000_000) - price
            if price_diff >= threshold and price < selected_price:
                selected_language = language
                selected_price = price
        chosen_languages[card] = selected_language
    return chosen_languages


def choose_languages3(prices_by_lang: dict[str, dict[str, int]], config: dict[str, int]) -> dict[str, str]:
    """Apply per-step and accumulated savings thresholds in configured language order."""
    chosen_languages: dict[str, str] = {}
    base_language = next(iter(config))
    base_prices = prices_by_lang.get(base_language, {})
    all_cards = {card for prices in prices_by_lang.values() for card in prices}
    for card in all_cards:
        selected_language = None
        selected_price = None
        accumulated_threshold = 0
        for language, threshold in config.items():
            accumulated_threshold += threshold
            price = prices_by_lang.get(language, {}).get(card)
            if price is None:
                continue
            if selected_language is None or selected_price is None:
                selected_language = language
                selected_price = price
                continue
            base_price = base_prices.get(card, 1_000_000_000)
            price_diff_from_selected = selected_price - price
            price_diff_from_base = base_price - price
            print(f"[DEBUG] {card=} {selected_language=} {language=} {selected_price=} {price=} {base_price=} ")
            if price_diff_from_selected >= threshold and price_diff_from_base >= accumulated_threshold:
                print(f"[DEBUG] Choosing language {language!r}")
                selected_language = language
                selected_price = price
            else:
                print(f"[DEBUG] Not choosing language {language!r}")
        if selected_language is not None:
            chosen_languages[card] = selected_language
        print()
    return chosen_languages


def price_per_card_cents(price_text: str, quantity: int) -> int:
    value = price_text.replace("€", "").replace("\xa0", "").replace(",", ".").strip()
    return round(float(value) * 100) // quantity
