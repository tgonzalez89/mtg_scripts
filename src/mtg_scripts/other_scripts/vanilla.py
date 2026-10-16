"""Fetch vanilla creatures from Scryfall and rank them by efficiency.

The script searches Scryfall for vanilla creatures matching the supplied query,
then ranks them by power divided by mana value, followed by power, toughness,
and card name. The output is written to a plain text file with an efficiency
column showing the power-to-mana-value ratio as a float.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict

from mtg_scripts.services.scryfall import ScryfallService

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtg_scripts.services.scryfall.models import ScryfallCard

DEFAULT_QUERY: Final = "type:creature commander:wg (game:paper) is:vanilla"
DEFAULT_OUTPUT: Final = Path("vanilla_creatures.txt")


class RankedCard(TypedDict):
    """A vanilla creature annotated with its computed efficiency ranking."""

    name: str
    mana_value: int
    mana_cost: str
    power: int
    toughness: int
    efficiency: float


def fetch_scryfall_cards(query: str = DEFAULT_QUERY, service: ScryfallService | None = None) -> list[ScryfallCard]:
    """Fetch all cards returned by a Scryfall search query."""
    if service is None:
        with ScryfallService() as owned_service:
            return fetch_scryfall_cards(query, owned_service)
    result = service.search(query, order="cmc", direction="asc")
    return list(result.cards)


def is_vanilla_creature(card: ScryfallCard) -> bool:
    type_line = card.type_line.lower()

    if not type_line:
        return True

    if "token" in type_line:
        return False

    return "creature" in type_line


def parse_numeric_value(value: float | str | None) -> int | None:
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
    cards: list[ScryfallCard], min_mana_value: int | None = None, min_power: int | None = None
) -> list[RankedCard]:
    ranked: list[RankedCard] = []

    for card in cards:
        if not is_vanilla_creature(card):
            continue

        mana_value = parse_numeric_value(card.mana_value)
        power = parse_numeric_value(card.power)
        toughness = parse_numeric_value(card.toughness)

        if mana_value is None or power is None or toughness is None:
            continue

        if min_mana_value is not None and mana_value < min_mana_value:
            continue

        if min_power is not None and power < min_power:
            continue

        efficiency = float(power) / float(mana_value) if mana_value else 0.0

        ranked.append(
            RankedCard(
                name=card.name,
                mana_value=mana_value,
                mana_cost=card.mana_cost,
                power=power,
                toughness=toughness,
                efficiency=efficiency,
            )
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


def format_card_line(card: RankedCard) -> str:
    return (
        f"{card['name']} | {card['mana_value']} | {card['mana_cost']} | "
        f"{card['power']}/{card['toughness']} | {format_efficiency(card['efficiency'])}"
    )


def write_output(cards: list[RankedCard], output_path: Path) -> None:
    lines = [format_card_line(card) for card in cards]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

    try:
        cards = fetch_scryfall_cards(args.query)
        ranked_cards = rank_cards(cards, min_mana_value=args.min_mana_value, min_power=args.min_power)
        output_path = Path(args.output)
        write_output(ranked_cards, output_path)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

    print(f"Wrote {len(ranked_cards)} cards to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
