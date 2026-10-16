"""Color identity, fetchland, group-price, and specific-land policies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .scryfall import query_scryfall

if TYPE_CHECKING:
    from mtg_scripts.services.scryfall import ScryfallService
    from mtg_scripts.services.scryfall.models import ScryfallCard

    from .models import CardFilterConfig


def _is_fetchland_group(group: str | None) -> bool:
    return bool(group and (group == "otag:cycle-ala-panorama" or "fetchland" in group))


def _fetches_allowed_color(oracle_text: str, colors: str, *, allow_off_color_lands: bool) -> bool:
    basic_land_names = {"w": "Plains", "u": "Island", "b": "Swamp", "r": "Mountain", "g": "Forest"}
    matching_colors = [color for color, land in basic_land_names.items() if land in oracle_text and color in colors]
    found_colors = [color for color, land in basic_land_names.items() if land in oracle_text]
    return bool(matching_colors) if allow_off_color_lands else len(found_colors) == len(matching_colors)


def should_remove_fetchland(
    card: ScryfallCard,
    group: str | None,
    colors: str,
    *,
    allow_off_color_lands: bool,
    service: ScryfallService | None = None,
) -> bool:
    if not bool(group):
        tagged_cards = service.cards_for_tag("fetchland") if service is not None else None
        if tagged_cards is None or len(tagged_cards) == 0:
            query = f'game:paper legal:commander order:usd dir:asc otag:fetchland !"{card.name}"'
            data = query_scryfall(query, service)
            is_fetchland = bool(data and data[0].name == card.name)
        else:
            is_fetchland = any(tagged.name.casefold() == card.name.casefold() for tagged in tagged_cards)
        if is_fetchland:
            group = "fetchland"

    if not _is_fetchland_group(group):
        return False
    return not _fetches_allowed_color(card.oracle_text, colors, allow_off_color_lands=allow_off_color_lands)


def is_color_identity_matching(card: ScryfallCard, colors: str) -> bool:
    color_identity = card.color_identity
    if not color_identity:
        return True
    return {color.casefold() for color in color_identity}.issubset(set(colors))


def process_cards(
    cards: list[ScryfallCard],
    config: CardFilterConfig,
    group: str | None,
    service: ScryfallService | None = None,
) -> dict[str, float]:
    processed_cards: dict[str, float] = {}
    for card in cards:
        if not is_color_identity_matching(card, config.colors):
            continue
        if should_remove_fetchland(
            card, group, config.colors, allow_off_color_lands=config.allow_off_color_lands, service=service
        ):
            restriction = "" if config.allow_off_color_lands else "strict "
            subject = f" from group '{group}'" if bool(group) else ""
            print(f"Removing card '{card.name}'{subject} due to {restriction}off-color restriction.")
            continue

        price = get_price(config.price_source, card)
        if group == "" and price > config.max_price_specific_lands:
            print(f"Removing card '{card.name}' because its price is above the specific-land limit.")
            continue
        processed_cards[card.name] = price

    if processed_cards and bool(group):
        average_price = sum(processed_cards.values()) / len(processed_cards)
        print(f'"{group}": {average_price:.2f}')
        if average_price > config.max_price_group_average:
            print(f"Removing group '{group}' because its average price is above the group limit.")
            return {}
    return processed_cards


def get_price(price_source: str, card: ScryfallCard) -> float:
    prices = card.prices
    direct_price = prices.get(price_source)
    if direct_price is not None:
        return float(direct_price)

    possible_prices = [
        float(price) for name, price in prices.items() if name.startswith(price_source) and price is not None
    ]
    if possible_prices:
        return min(possible_prices)
    print(f"Error fetching price for card '{card.name}' with price source '{price_source}'.")
    return float("inf")
