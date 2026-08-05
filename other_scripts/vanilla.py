"""Fetch vanilla creatures from Scryfall and rank them by efficiency.

The script searches Scryfall for vanilla creatures matching the supplied query,
then ranks them by power divided by mana value, followed by power, toughness,
and card name. The output is written to a plain text file with an efficiency
column showing the power-to-mana-value ratio as a float.
"""

from __future__ import annotations

import argparse
import urllib.parse
from pathlib import Path
from typing import Any

import requests

DEFAULT_QUERY = "type:creature commander:wg (game:paper) is:vanilla"
DEFAULT_OUTPUT = Path(__file__).with_name("vanilla_creatures.txt")


def fetch_scryfall_cards(query: str = DEFAULT_QUERY) -> list[dict[str, Any]]:
    """Fetch all cards returned by a Scryfall search query."""
    cards: list[dict[str, Any]] = []
    page = 1

    while True:
        params = {
            "q": query,
            "page": page,
            "order": "cmc",
            "dir": "asc",
        }
        url = "https://api.scryfall.com/cards/search"
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": "mtg-scripts/vanilla"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        data = payload.get("data", [])
        cards.extend(data)

        if not payload.get("has_more", False):
            break

        next_page = payload.get("next_page")
        if next_page is None:
            break

        parsed = urllib.parse.urlparse(str(next_page))
        query_params = urllib.parse.parse_qs(parsed.query)
        page_value = query_params.get("page", [page + 1])[0]
        page = int(page_value)

    return cards


def is_vanilla_creature(card: dict[str, Any]) -> bool:
    type_line = str(card.get("type_line", "")).lower()

    if not type_line:
        return True

    if "token" in type_line:
        return False

    return "creature" in type_line


def parse_numeric_value(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip()
    if not text or text == "*":
        return None

    try:
        return int(text)
    except ValueError:
        return None


def rank_cards(
    cards: list[dict[str, Any]], min_mana_value: int | None = None, min_power: int | None = None
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []

    for card in cards:
        if not is_vanilla_creature(card):
            continue

        mana_value = parse_numeric_value(card.get("mana_value"))
        if mana_value is None:
            mana_value = parse_numeric_value(card.get("cmc"))

        power = parse_numeric_value(card.get("power"))
        toughness = parse_numeric_value(card.get("toughness"))

        if mana_value is None or power is None or toughness is None:
            continue

        if min_mana_value is not None and mana_value < min_mana_value:
            continue

        if min_power is not None and power < min_power:
            continue

        efficiency = float(power) / float(mana_value) if mana_value else 0.0

        ranked.append(
            {
                "name": card.get("name", "Unknown"),
                "mana_value": mana_value,
                "mana_cost": card.get("mana_cost", ""),
                "power": power,
                "toughness": toughness,
                "efficiency": efficiency,
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["efficiency"],
            -item["power"],
            -item["toughness"],
            item["name"].lower(),
        )
    )
    return ranked


def format_efficiency(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    if "." not in text:
        text = f"{text}.0"
    return text


def format_card_line(card: dict[str, Any]) -> str:
    return (
        f"{card['name']} | {card['mana_value']} | {card['mana_cost']} | "
        f"{card['power']}/{card['toughness']} | {format_efficiency(card['efficiency'])}"
    )


def write_output(cards: list[dict[str, Any]], output_path: Path) -> None:
    lines = [format_card_line(card) for card in cards]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and rank vanilla creatures from Scryfall")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Scryfall search query")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path to save the ranked output text file",
    )
    parser.add_argument(
        "--min-mana-value",
        type=int,
        default=None,
        help="Only include cards with mana value greater than or equal to this value",
    )
    parser.add_argument(
        "--min-power",
        type=int,
        default=None,
        help="Only include cards with power greater than or equal to this value",
    )
    args = parser.parse_args()

    cards = fetch_scryfall_cards(args.query)
    ranked_cards = rank_cards(cards, min_mana_value=args.min_mana_value, min_power=args.min_power)
    output_path = Path(args.output)
    write_output(ranked_cards, output_path)

    print(f"Wrote {len(ranked_cards)} cards to {output_path}")


if __name__ == "__main__":
    main()
