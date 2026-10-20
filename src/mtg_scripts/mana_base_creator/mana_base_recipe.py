"""Run the mana-base creator with a named budget and land theme."""

from __future__ import annotations

import argparse
import shlex
from typing import TYPE_CHECKING

from mtg_scripts.mana_base_creator.mana_base_creator import (
    creator_config_from_namespace,
)
from mtg_scripts.mana_base_creator.mana_base_creator import (
    parse_arguments as parse_creator_arguments,
)
from mtg_scripts.mana_base_creator.mana_base_creator import (
    run_creator_config as run_creator,
)
from mtg_scripts.mana_base_creator.models import CreatorConfig

if TYPE_CHECKING:
    from collections.abc import Sequence

BUDGETS = {
    "ultra-low": (10, 1),
    "very-low": (20, 2),
    "low": (30, 3),
    "medium": (50, 5),
    "high": (100, 10),
    "very-high": (200, 20),
    "ultra-high": (500, 50),
    "extreme": (1000, 100),
    "ultra-extreme": (10000, 1000),
    "unlimited": (100000, 10000),
}

MDFC_UNTAPPED_QUERY = 'is:mdfc t:land -produces:m o:"may pay 3 life"'
MDFC_TAPPED_QUERY = 'is:mdfc t:land -produces:m o:"This land enters tapped."'

THEMES = {
    "all": (
        [
            "otag:cycle-fetchland",
            "otag:cycle-abu-dual-land",
            "otag:tricycle-land",
            "otag:cycle-shockland",
            "otag:cycle-dual-surveil-land",
            "otag:cycle-bondland",
            "otag:cycle-triple-tapland",
            "otag:cycle-painland",
            "otag:cycle-soc-turbulent-land",
            "otag:cycle-slowland",
            "otag:cycle-fastland",
            "otag:cycle-verge",
            "otag:cycle-msh-lair-dual",
            "otag:cycle-tor-tainted-land",
            "otag:cycle-checkland",
            "otag:cycle-tangoland",
            "otag:cycle-reveal-land",
            "otag:cycle-pathway",
            "otag:cycle-horizon-land",
            "otag:cycle-hybrid-filterland",
            "otag:cycle-ody-filterland",
            "otag:cycle-bicycle-land",
            "otag:cycle-mh3-mdfc-dual-land",
            "otag:cycle-scry-land",
            "otag:cycle-mh3-landscape",
            "otag:cycle-snc-fetchland",
            "otag:cycle-ala-panorama",
            "otag:cycle-rav-bounceland",
            MDFC_UNTAPPED_QUERY,
            MDFC_TAPPED_QUERY,
        ],
        [
            "Command Tower",
            "Exotic Orchard",
            "Fabled Passage",
            "Prismatic Vista",
            "Reflecting Pool",
            "Mana Confluence",
            "City of Brass",
            "Multiversal Passage",
            "Horizon of Progress",
        ],
    ),
    "all-duals": (
        [
            "otag:cycle-fetchland",
            "otag:cycle-abu-dual-land",
            "otag:tricycle-land",
            "otag:cycle-shockland",
            "otag:cycle-dual-surveil-land",
            "otag:cycle-bondland",
            "otag:cycle-triple-tapland",
            "otag:cycle-painland",
            "otag:cycle-soc-turbulent-land",
            "otag:cycle-slowland",
            "otag:cycle-fastland",
            "otag:cycle-verge",
            "otag:cycle-msh-lair-dual",
            "otag:cycle-tor-tainted-land",
            "otag:cycle-checkland",
            "otag:cycle-tangoland",
            "otag:cycle-reveal-land",
            "otag:cycle-pathway",
            "otag:cycle-horizon-land",
            "otag:cycle-hybrid-filterland",
            "otag:cycle-ody-filterland",
            "otag:cycle-bicycle-land",
            "otag:cycle-mh3-mdfc-dual-land",
            "otag:cycle-scry-land",
            "otag:cycle-mh3-landscape",
            "otag:cycle-snc-fetchland",
            "otag:cycle-ala-panorama",
            "otag:cycle-rav-bounceland",
        ],
        [
            "Command Tower",
            "Exotic Orchard",
            "Fabled Passage",
            "Prismatic Vista",
            "Reflecting Pool",
            "Mana Confluence",
            "City of Brass",
            "Multiversal Passage",
            "Horizon of Progress",
        ],
    ),
    "basic-types": (
        [
            "otag:cycle-fetchland",
            "otag:cycle-abu-dual-land",
            "otag:tricycle-land",
            "otag:cycle-shockland",
            "otag:cycle-dual-surveil-land",
            "otag:cycle-soc-turbulent-land",
            "otag:cycle-verge",
            "otag:cycle-msh-lair-dual",
            "otag:cycle-tor-tainted-land",
            "otag:cycle-checkland",
            "otag:cycle-tangoland",
            "otag:cycle-reveal-land",
            "otag:cycle-bicycle-land",
        ],
        ["Command Tower", "Fabled Passage", "Prismatic Vista", "Multiversal Passage", "Horizon of Progress"],
    ),
    "untapped": (
        [
            "otag:cycle-fetchland",
            "otag:cycle-abu-dual-land",
            "otag:cycle-shockland",
            "otag:cycle-bondland",
            "otag:cycle-painland",
            "otag:cycle-msh-lair-dual",
            "otag:cycle-tor-tainted-land",
            "otag:cycle-pathway",
            "otag:cycle-horizon-land",
            "otag:cycle-hybrid-filterland",
            "otag:cycle-ody-filterland",
        ],
        [
            "Command Tower",
            "Exotic Orchard",
            "Prismatic Vista",
            "Reflecting Pool",
            "Mana Confluence",
            "City of Brass",
            "Multiversal Passage",
            "Horizon of Progress",
        ],
    ),
    "mdfcs-all": (
        ["otag:cycle-mh3-mdfc-dual-land", MDFC_UNTAPPED_QUERY, MDFC_TAPPED_QUERY],
        [],
    ),
    "mdfcs-dual-and-untapped": (
        ["otag:cycle-mh3-mdfc-dual-land", MDFC_UNTAPPED_QUERY],
        [],
    ),
}


def parse_arguments(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Create a Commander mana base using a named budget and land theme.")
    parser.add_argument("budget", choices=BUDGETS)
    parser.add_argument("theme", choices=THEMES)
    parser.add_argument("colors")
    parser.add_argument("total_lands", type=int)
    parser.add_argument("min_basics", type=int)
    parser.add_argument("price_source", choices=["usd", "eur", "tix"])
    return parser.parse_known_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args, extra_options = parse_arguments(argv)
    budget, max_price = BUDGETS[args.budget]
    groups, lands = THEMES[args.theme]

    preset = CreatorConfig(
        colors=args.colors.casefold(),
        total_lands=args.total_lands,
        min_basics=args.min_basics,
        budget=float(budget),
        max_price_group_average=float(max_price),
        max_price_specific_lands=float(max_price),
        price_source=args.price_source,
        enable_groups=tuple(groups),
        disable_groups=(),
        enable_specific_lands=tuple(lands),
        disable_specific_lands=(),
        allow_off_color_lands=False,
        allow_stale_data=False,
    )
    creator_args = [
        "--colors",
        args.colors,
        "--total-lands",
        str(args.total_lands),
        "--min-basics",
        str(args.min_basics),
        "--budget",
        str(budget),
        "--max-price-group-average",
        str(max_price),
        "--max-price-specific-lands",
        str(max_price),
        "--price-source",
        args.price_source,
        "--enable-groups",
        *groups,
        "--enable-specific-lands",
        *lands,
        *extra_options,
    ]

    print("Running creator with arguments:")
    print(shlex.join(creator_args), flush=True)
    creator_options = creator_config_from_namespace(parse_creator_arguments(extra_options, defaults=preset))
    return run_creator(creator_options)


if __name__ == "__main__":
    raise SystemExit(main())
