#!/bin/env python3
import argparse
import sys
from collections.abc import Sequence  # noqa: TC003

from mtg_scripts.services.scryfall import ScryfallService

from .allocation import (
    add_land_groups as _add_land_groups,
)
from .allocation import (
    add_specific_lands as _add_specific_lands,
)
from .allocation import (
    fill_basic_lands as _fill_basic_lands,
)
from .allocation import (
    render_mana_base as _print_mana_base,
)
from .candidate_acquisition import (
    filter_candidates as _filter_candidates,
)
from .models import CardFilterConfig, CreatorConfig, ManaBaseLimits


def parse_arguments(argv: Sequence[str] | None = None, *, defaults: CreatorConfig | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a mana base for a Commander deck in Magic: The Gathering.")

    parser.add_argument(
        "--colors",
        type=str,
        required=defaults is None,
        default=None if defaults is None else defaults.colors,
        help='Colors of the deck (e.g., "WUBRG")',
    )
    parser.add_argument("--total-lands", type=int, default=40, help="Total number of lands in the deck")
    parser.add_argument("--min-basics", type=int, default=5, help="Minimum number of basic lands")
    parser.add_argument("--budget", type=float, default=500.0, help="Total budget for lands")
    parser.add_argument(
        "--max-price-group-average",
        type=float,
        default=50.0,
        help="Maximum average price for each of the groups of lands specified in --enable-groups",
    )
    parser.add_argument(
        "--max-price-specific-lands",
        type=float,
        default=50.0,
        help="Maximum price for each of the lands specified in --enable-specific-lands",
    )
    parser.add_argument(
        "--price-source",
        type=str,
        default="usd",
        choices=["usd", "eur", "tix"],
        help="Source for card prices",
    )
    parser.add_argument(
        "--allow-stale-data",
        action="store_true",
        help="Allow cached Scryfall card prices that have exceeded the freshness period",
    )
    parser.add_argument(
        "--enable-groups",
        type=str,
        nargs="*",
        help="Enable specific groups of lands (Scryfall queries)",
        default=[
            "otag:cycle-fetchland",  # Fetchlands
            "otag:cycle-abu-dual-land",  # Original duals, untapped, fetchable
            "otag:tricycle-land",  # Triomes, enter tapped, cycling for {3}, fetchable
            "otag:cycle-shockland",  # Untapped if 2 damage, fetchable
            "otag:cycle-dual-surveil-land",  # Enter tapped, surveil 1, fetchable
            "otag:cycle-bondland",  # Untapped if >=2 opponents
            "otag:cycle-triple-tapland",  # Cheap triomes
            "otag:cycle-painland",  # Tap for {C}, dual for 1 damage
            "otag:cycle-soc-turbulent-land",  # Untapped if opponents to control >=8 lands, fetchable
            "otag:cycle-slowland",  # Untapped if >=2 other lands
            "otag:cycle-fastland",  # Untapped if <=2 other lands
            "otag:cycle-verge",  # Tap for one color, for the other if control one of the two basic types
            "otag:cycle-msh-lair-dual",  # Tap for {C}, dual if control a basic or a land entered this turn
            "otag:cycle-tor-tainted-land",  # Tap for {C}, dual if control a swamp
            "otag:cycle-checkland",  # Untapped if control one of the two basic types
            "otag:cycle-tangoland",  # Untapped if control 2 basic lands, fetchable
            "otag:cycle-reveal-land",  # Untapped if reveal one of the two basic types
            "otag:cycle-pathway",  # MDFC dual lands
            "otag:cycle-horizon-land",  # Dual for 1 damage, can be sacrificed to draw a card
            "otag:cycle-hybrid-filterland",  # Hybrid mana filter dual lands, add one of each
            "otag:cycle-ody-filterland",  # Signet-style filter dual lands, add one of each
            "otag:cycle-bicycle-land",  # Enter tapped, cycling, fetchable
            "otag:cycle-mh3-mdfc-dual-land",  # MDFC dual lands with spells in the front
            "otag:cycle-scry-land",  # Enter tapped, scry 1
            "otag:cycle-mh3-landscape",  # Basic tri fetches, tap for {C}, can be cycled for 3 colored mana
            "otag:cycle-snc-fetchland",  # Basic tri fetches, are sacrificed automatically and gain 1 life
            "otag:cycle-ala-panorama",  # Basic tri fetches, tap for add {C}, cost {1} to fetch
            "otag:cycle-rav-bounceland",  # Bouncelands, enter tapped, add one of each
            'is:mdfc t:land -produces:m o:"may pay 3 life"',  # MDFC lands that can enter untapped for 3 life
            'is:mdfc t:land -produces:m o:"This land enters tapped."',  # MDFC lands that always enter tapped
        ],
    )
    parser.add_argument(
        "--disable-groups",
        type=str,
        nargs="*",
        default=[],
        help="Disable specific groups of lands (Scryfall queries)",
    )
    parser.add_argument(
        "--enable-specific-lands",
        type=str,
        nargs="*",
        help="Enable specific lands (exact names)",
        default=[
            "Command Tower",  # Tap for any color of mana from your commander
            "Exotic Orchard",  # Tap for any color of mana that a land an opponent could produce
            "Fabled Passage",  # Basic fetchland, fetches land enters tapped unless >= 4 lands
            "Prismatic Vista",  # Basic fetchland
            "Reflecting Pool",  # Tap for any color of mana that a land you control could produce
            "Mana Confluence",  # Painland
            "City of Brass",  # Painland
            "Multiversal Passage",  # Basic shockland, you choose 1 basic land type for it to be
        ],
    )
    parser.add_argument(
        "--disable-specific-lands",
        type=str,
        nargs="*",
        default=[],
        help="Disable specific lands (exact names)",
    )
    parser.add_argument("--allow-off-color-lands", action="store_true", help="Allow off-color lands")
    if defaults is not None:
        parser.set_defaults(
            total_lands=defaults.total_lands,
            min_basics=defaults.min_basics,
            budget=defaults.budget,
            max_price_group_average=defaults.max_price_group_average,
            max_price_specific_lands=defaults.max_price_specific_lands,
            price_source=defaults.price_source,
            enable_groups=defaults.enable_groups,
            disable_groups=defaults.disable_groups,
            enable_specific_lands=defaults.enable_specific_lands,
            disable_specific_lands=defaults.disable_specific_lands,
            allow_off_color_lands=defaults.allow_off_color_lands,
            allow_stale_data=defaults.allow_stale_data,
        )
    args = parser.parse_args(argv)

    # Make colors uppercase and check for duplicates, validate that colors are valid (WUBRGC).
    if len(args.colors.casefold()) != len(set(args.colors.casefold())):
        msg = "Duplicate colors specified. Each color should be unique."
        parser.error(msg)
    args.colors = args.colors.casefold()
    valid_colors = set("wubrg")
    colorless_colors = set("c")
    if not set(args.colors).issubset(valid_colors) and not set(args.colors).issubset(colorless_colors):
        msg = "Invalid colors specified. Valid colors are [W, U, B, R, G], or C."
        parser.error(msg)

    # Make all group and specific land names lowercase for consistency.
    args.enable_groups = [group.casefold() for group in args.enable_groups]
    args.disable_groups = [group.casefold() for group in args.disable_groups]
    args.enable_specific_lands = [land.casefold() for land in args.enable_specific_lands]
    args.disable_specific_lands = [land.casefold() for land in args.disable_specific_lands]

    return args


def creator_config_from_namespace(args: argparse.Namespace) -> CreatorConfig:
    return CreatorConfig(
        colors=args.colors,
        total_lands=args.total_lands,
        min_basics=args.min_basics,
        budget=args.budget,
        max_price_group_average=args.max_price_group_average,
        max_price_specific_lands=args.max_price_specific_lands,
        price_source=args.price_source,
        enable_groups=tuple(args.enable_groups),
        disable_groups=tuple(args.disable_groups),
        enable_specific_lands=tuple(args.enable_specific_lands),
        disable_specific_lands=tuple(args.disable_specific_lands),
        allow_off_color_lands=args.allow_off_color_lands,
        allow_stale_data=args.allow_stale_data,
    )


def _run(config: CreatorConfig) -> None:
    filter_config = CardFilterConfig(
        colors=config.colors,
        price_source=config.price_source,
        max_price_group_average=config.max_price_group_average,
        max_price_specific_lands=config.max_price_specific_lands,
        allow_off_color_lands=config.allow_off_color_lands,
    )
    with ScryfallService(allow_stale_data=config.allow_stale_data) as service:
        groups_cards, specific_lands_cards = _filter_candidates(config, filter_config, service)
    limits = ManaBaseLimits(config.colors, config.budget, config.total_lands, config.min_basics)
    lands: list[str] = []
    total_price = 0.0
    total_price = _add_specific_lands(limits, lands, total_price, specific_lands_cards)
    total_price = _add_land_groups(limits, lands, total_price, groups_cards)
    _fill_basic_lands(limits, lands)
    _print_mana_base(lands, total_price)


def run_creator_config(config: CreatorConfig) -> int:
    try:
        _run(config)
    except (OSError, TypeError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_creator_config(creator_config_from_namespace(parse_arguments(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
