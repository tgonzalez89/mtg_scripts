"""Run the mana-base creator with a named budget and land theme."""

import argparse
import shlex

from mtg_scripts.mana_base_creator.mana_base_creator import main as run_creator

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
        ["Command Tower", "Fabled Passage", "Prismatic Vista", "Multiversal Passage"],
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
        ],
    ),
    "mdfcs-all": (
        ["otag:cycle-mh3-mdfc-dual-land", MDFC_UNTAPPED_QUERY, MDFC_TAPPED_QUERY],
        [],
    ),
    "mdfcs-dual-untapped": (
        ["otag:cycle-mh3-mdfc-dual-land", MDFC_UNTAPPED_QUERY],
        [],
    ),
}


def parse_arguments() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Create a Commander mana base using a named budget and land theme.")
    parser.add_argument("budget", choices=BUDGETS)
    parser.add_argument("theme", choices=THEMES)
    parser.add_argument("colors")
    parser.add_argument("total_lands", type=int)
    parser.add_argument("min_basics", type=int)
    parser.add_argument("price_source", choices=["usd", "eur", "tix"])
    return parser.parse_known_args()


def main() -> None:
    args, extra_options = parse_arguments()
    budget, max_price = BUDGETS[args.budget]
    groups, lands = THEMES[args.theme]

    creator_args = [
        "--colors",
        args.colors,
        "--total_lands",
        str(args.total_lands),
        "--min_basics",
        str(args.min_basics),
        "--budget",
        str(budget),
        "--max_price_group_average",
        str(max_price),
        "--max_price_specific_lands",
        str(max_price),
        "--price_source",
        args.price_source,
        "--enable_groups",
        *groups,
        "--enable_specific_lands",
        *lands,
        *extra_options,
    ]

    print("Running creator with arguments:")
    print(shlex.join(creator_args), flush=True)
    run_creator(creator_args)


if __name__ == "__main__":
    main()
