"""Compare older bordered sets with Premodern and filter format-banned cards."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from mtg_scripts.services.scryfall import ScryfallCard, ScryfallService, TerminalProgressIndicator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtg_scripts.services.scryfall.models import ScryfallSearchResult

type CardList = list[ScryfallCard]
type Report = tuple[CardList, CardList, CardList]

PREMODERN_SETS: Final = (
    ("4ed", "Fourth Edition"),
    ("ice", "Ice Age"),
    ("chr", "Chronicles"),
    ("hml", "Homelands"),
    ("all", "Alliances"),
    ("mir", "Mirage"),
    ("vis", "Visions"),
    ("5ed", "Fifth Edition"),
    ("wth", "Weatherlight"),
    ("tmp", "Tempest"),
    ("sth", "Stronghold"),
    ("exo", "Exodus"),
    ("usg", "Urza's Saga"),
    ("ulg", "Urza's Legacy"),
    ("6ed", "Classic Sixth Edition"),
    ("uds", "Urza's Destiny"),
    ("mmq", "Mercadian Masques"),
    ("nem", "Nemesis"),
    ("pcy", "Prophecy"),
    ("inv", "Invasion"),
    ("pls", "Planeshift"),
    ("7ed", "Seventh Edition"),
    ("apc", "Apocalypse"),
    ("ody", "Odyssey"),
    ("tor", "Torment"),
    ("jud", "Judgment"),
    ("ons", "Onslaught"),
    ("lgn", "Legions"),
    ("scg", "Scourge"),
)
OLDER_BORDERED_SETS: Final = (
    ("lea", "Limited Edition Alpha"),
    ("leb", "Limited Edition Beta"),
    ("2ed", "Unlimited Edition"),
    ("3ed", "Revised Edition"),
    ("arn", "Arabian Nights"),
    ("atq", "Antiquities"),
    ("leg", "Legends"),
    ("drk", "The Dark"),
    ("fem", "Fallen Empires"),
)
BANNED_QUERIES: Final = (
    ("legacy", "banned:legacy"),
    ("vintage", "banned:vintage"),
    ("restricted_vintage", "restricted:vintage"),
    ("dual_lands", "is:dual"),
)
MANUALLY_BANNED_CARDS: Final = (
    # From historical bans + Pauper
    # When a card appears in multiple formats, list it under the strongest format.
    # B&R strength order: Vintage > Legacy > Pauper > Extended > Standard.
    # - Highest format: Standard -
    # - Highest format: Extended -
    # "Juggernaut",
    # "Kird Ape",
    # "Serendib Efreet",
    # - Highest format: Pauper -
    "High Tide",
    # "Sinkhole",
    # - Highest format: Legacy -
    # "Illusionary Mask",
    "Hymn to Tourach",
    # - Highest format: Vintage -
    # "Ali from Cairo",
    # "Braingeyser",
    # "Berserk",
    # "Copy Artifact",
    # "Divine Intervention",
    # "Fork",
    # "Gauntlet of Might",
    # "Maze of Ith",
    # "Mirror Universe",
    # "Regrowth",
    # "Rukh Egg",
    # "Sword of the Ages",
    # "Underworld Dreams",
    #
    # Other cards that have not been banned other formats but maybe are too strong
    # "The Tabernacle at Pendrell Vale",
)
OUTPUT_TEXT_FILENAMES: Final = {
    "additions": "intermediate_additions.txt",
    "new_bans": "new_bans.txt",
    "final": "final_pool.txt",
}


def build_set_query(sets: Sequence[tuple[str, str]]) -> str:
    """Build one Scryfall query covering a group of included core sets and expansions."""
    set_codes = (code for code, _ in sets)
    return "(" + " or ".join(f"set:{code}" for code in set_codes) + ")"


def fetch_cards(service: ScryfallService) -> tuple[list[ScryfallCard], dict[str, set[str]]]:
    """Fetch unique cards from both set groups and the applicable format ban lists."""
    premodern_result = service.search(build_set_query(PREMODERN_SETS), unique="cards")
    older_result = service.search(build_set_query(OLDER_BORDERED_SETS), unique="cards")
    set_cards = [*premodern_result.cards, *older_result.cards]
    _require_oracle_ids(set_cards)
    legality_ids: dict[str, set[str]] = {}
    for reason, query in BANNED_QUERIES:
        result = service.search(query, unique="cards")
        if not result.cards:
            message = f"Scryfall returned no cards for the required legality query {query!r}."
            raise RuntimeError(message)
        legality_ids[reason] = _oracle_ids(result)
    return set_cards, legality_ids


def build_lists(cards: Sequence[ScryfallCard], legality_ids: dict[str, set[str]]) -> Report:
    """Return intermediate additions, the proposed new ban list, and the final pool."""
    premodern_codes = {code for code, _ in PREMODERN_SETS}
    premodern_ids = {card.oracle_id for card in cards if card.set_code in premodern_codes and not card.is_token}

    additions_by_id: dict[str, ScryfallCard] = {}
    old_set_codes = {code for code, _ in OLDER_BORDERED_SETS}
    for card in cards:
        if card.set_code not in old_set_codes or card.is_token or card.oracle_id in premodern_ids:
            continue
        if not card.oracle_id:
            message = f"Scryfall printing {card.print_id!r} is missing its Oracle ID."
            raise ValueError(message)
        additions_by_id.setdefault(card.oracle_id, card)

    additions = sorted(additions_by_id.values(), key=lambda card: card.name.casefold())
    manually_banned_names = {name.casefold() for name in MANUALLY_BANNED_CARDS}
    new_bans: list[ScryfallCard] = []
    final_pool: list[ScryfallCard] = []
    for addition in additions:
        if addition.name.casefold() in manually_banned_names or any(
            addition.oracle_id in legality_ids[reason] for reason, _ in BANNED_QUERIES
        ):
            new_bans.append(addition)
        else:
            final_pool.append(addition)

    return additions, new_bans, final_pool


def write_report(
    output_dir: Path,
    report: Report,
) -> None:
    """Write plain-text files containing only unique card names."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for key, cards in zip(("additions", "new_bans", "final"), report, strict=True):
        names = [card.name for card in cards]
        text = "\n".join(names)
        (output_dir / OUTPUT_TEXT_FILENAMES[key]).write_text(text + ("\n" if text else ""), encoding="utf-8")


def _oracle_ids(result: ScryfallSearchResult) -> set[str]:
    return _require_oracle_ids(result.cards, context="legality")


def _require_oracle_ids(cards: Sequence[ScryfallCard], *, context: str = "set") -> set[str]:
    if any(not card.oracle_id for card in cards):
        message = f"A Scryfall {context} result contains a card without an Oracle ID."
        raise ValueError(message)
    return {card.oracle_id for card in cards}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare older bordered sets with Premodern and filter banned or restricted cards."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("theoretical_premodern_results"),
        help="Directory for the intermediate, proposed new-ban, and final card lists",
    )
    args = parser.parse_args(argv)

    try:
        with ScryfallService(progress=TerminalProgressIndicator()) as service:
            cards, legality_ids = fetch_cards(service)
        report = build_lists(cards, legality_ids)
        write_report(args.output_dir, report)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

    additions, new_bans, final_pool = report
    print(f"Wrote {len(additions)} additions, {len(new_bans)} proposed new bans,")
    print(f"and {len(final_pool)} final cards to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
