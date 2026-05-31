import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

DEBUG = True


def parse_args():
    parser = argparse.ArgumentParser(description="Convert Moxfield deck IDs to Forge or XMage .dck files")

    parser.add_argument(
        "deck_ids",
        nargs="+",
        help="Moxfield deck IDs to convert",
    )

    parser.add_argument(
        "--format",
        "-f",
        choices=["forge", "xmage"],
        default="forge",
        help="Output format: forge or xmage (default: forge)",
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help=(
            "Output directory for .dck files. "
            "Forge default: %%APPDATA%%/Forge/decks/commander. "
            "XMage default: ~/Documents/xmage_decks."
        ),
    )

    parser.add_argument(
        "--no-override",
        "-n",
        action="store_true",
        help="Prompt user before overriding existing .dck files (default: override without prompting)",
    )

    args = parser.parse_args()
    return args


def get_default_output_dir(output_format: str) -> Path:
    """Get the default output directory for the selected format."""
    if output_format == "xmage":
        return Path.home() / "Documents" / "xmage_decks"

    appdata = os.getenv("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA environment variable not found")
    return Path(appdata) / "Forge" / "decks" / "commander"


def download_deck(deck_id: str) -> dict:
    """
    Download a deck from Moxfield API.

    Args:
        deck_id (str): Moxfield deck ID

    Returns:
        dict: Deck data from Moxfield API
    """
    moxfield_api_url = "https://api.moxfield.com/v2/decks/all/"
    headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"}
    request = urllib.request.Request(moxfield_api_url + deck_id, headers=headers)

    try:
        with urllib.request.urlopen(request) as response:
            if response.status != 200:
                print(f"Failed to get data from Moxfield. Status code: {response.status}")
                return None
            encoding = response.headers.get_content_charset("utf-8")
            data = json.loads(response.read().decode(encoding))
            if DEBUG:
                Path("debug.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - Failed to download deck {deck_id}")
        return None
    except Exception as e:
        print(f"Error downloading deck {deck_id}: {e}")
        return None


def extract_deck_sections(data: dict) -> tuple[str, dict, dict, dict, dict]:
    """
    Extract deck sections from Moxfield API response.

    Args:
        data (dict): Deck data from Moxfield API

    Returns:
        tuple: (deck_name, commanders, mainboard, sideboard, maybeboard)
        Each section is a dict: {card_name: {"quantity": qty, "layout": layout_type}}
    """
    deck_name = data.get("name", "Unnamed Deck")

    def process_section(section_data: dict) -> dict:
        """Process a deck section, extracting quantity, layout, set, and card number info."""
        processed = {}
        for card_name, card_data in section_data.items():
            card_info = card_data.get("card", {})
            layout = card_info.get("layout", "")
            set_code = card_info.get("set", "")
            card_number = card_info.get("cn", "")
            processed[card_name] = {
                "quantity": card_data["quantity"],
                "layout": layout,
                "set": set_code,
                "cn": card_number,
            }
        return processed

    commanders = process_section(data.get("commanders", {}))
    mainboard = process_section(data.get("mainboard", {}))
    sideboard = process_section(data.get("sideboard", {}))
    maybeboard = process_section(data.get("maybeboard", {}))

    return deck_name, commanders, mainboard, sideboard, maybeboard


def format_card_list(cards: dict) -> str:
    """
    Format a card dictionary into Forge card list format.
    Handles split cards (keeps ' // ') vs other double-faced cards (truncates at ' // ').

    Args:
        cards (dict): Mapping of card names to {"quantity": qty, "layout": layout_type}

    Returns:
        str: Formatted card list
    """
    lines = []
    for card_name in sorted(cards.keys()):
        card_info = cards[card_name]
        quantity = card_info["quantity"]
        layout = card_info.get("layout", "")

        display_name = card_name
        if layout != "split" and " // " in card_name:
            display_name = card_name.split(" // ")[0]

        lines.append(f"{quantity} {display_name}")
    return "\n".join(lines)


def format_xmage_card_list(cards: dict) -> str:
    """
    Format a card dictionary into XMage .dck format.

    Args:
        cards (dict): Mapping of card names to {"quantity": qty, "layout": layout_type, "set": set_code, "cn": card_number}

    Returns:
        str: Formatted XMage card list
    """
    lines = []
    for card_name in sorted(cards.keys()):
        card_info = cards[card_name]
        quantity = card_info["quantity"]
        layout = card_info.get("layout", "")
        set_code = card_info.get("set", "")
        card_number = card_info.get("cn", "")

        display_name = card_name
        if layout != "split" and " // " in card_name:
            display_name = card_name.split(" // ")[0]

        if set_code and card_number:
            lines.append(f"{quantity} [{set_code}:{card_number}] {display_name}")
        else:
            lines.append(f"{quantity} {display_name}")
    return "\n".join(lines)


def create_forge_dck_file(
    output_path: Path, deck_name: str, commanders: dict, mainboard: dict, sideboard: dict
) -> bool:
    """
    Create a .dck file in Forge format.

    Args:
        output_path (Path): Path where the .dck file should be created
        deck_name (str): Name of the deck
        commanders (dict): Commander cards
        mainboard (dict): Mainboard cards
        sideboard (dict): Sideboard cards

    Returns:
        bool: True if file was created, False if write failed
    """
    content = "[metadata]\n"
    content += f"name={deck_name}\n"

    if mainboard:
        content += "\n[Main]\n"
        content += format_card_list(mainboard)
        content += "\n"

    if commanders:
        content += "\n[Commander]\n"
        content += format_card_list(commanders)
        content += "\n"

    if sideboard:
        content += "\n[Sideboard]\n"
        content += format_card_list(sideboard)
        content += "\n"

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing file {output_path}: {e}")
        return False


def create_xmage_dck_file(output_path: Path, commanders: dict, mainboard: dict, sideboard: dict) -> bool:
    """
    Create a .dck file in XMage format.

    Args:
        output_path (Path): Path where the .dck file should be created
        commanders (dict): Commander cards
        mainboard (dict): Mainboard cards
        sideboard (dict): Sideboard cards

    Returns:
        bool: True if file was created, False if write failed
    """
    content = format_xmage_card_list(mainboard)

    side_lines = []
    for section in (commanders, sideboard):
        section_lines = format_xmage_card_list(section).splitlines()
        side_lines.extend(f"SB: {line}" for line in section_lines if line.strip())

    if side_lines:
        if content:
            content += "\n"
        content += "\n".join(side_lines)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing file {output_path}: {e}")
        return False


def main():
    args = parse_args()

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = get_default_output_dir(args.format)

    print(f"Output format: {args.format}")
    print(f"Output directory: {output_dir}")

    # Create output directory if it doesn't exist
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error creating output directory {output_dir}: {e}")
        sys.exit(1)

    successful = 0
    failed = 0

    for deck_id in args.deck_ids:
        print(f"\nProcessing deck: {deck_id}")

        data = download_deck(deck_id)
        if not data:
            failed += 1
            continue

        deck_name, commanders, mainboard, sideboard, maybeboard = extract_deck_sections(data)

        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in deck_name)
        safe_name = safe_name.strip() or "Unnamed_Deck"
        output_file = output_dir / f"{safe_name}.dck"

        print(f"Deck name: {deck_name}")
        print(f"Output file: {output_file}")
        print(f"  - Mainboard: {len(mainboard)} cards")
        print(f"  - Commanders: {len(commanders)} cards")
        print(f"  - Sideboard: {len(sideboard)} cards")

        if output_file.exists() and args.no_override:
            response = input(f"\n{output_file} already exists. Overwrite? (y/n): ").strip().lower()
            if response != "y":
                print("Skipped.")
                continue

        if args.format == "xmage":
            created = create_xmage_dck_file(output_file, commanders, mainboard, sideboard)
        else:
            created = create_forge_dck_file(output_file, deck_name, commanders, mainboard, sideboard)

        if created:
            print("Created successfully.")
            successful += 1
        else:
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"Summary: {successful} successful, {failed} failed")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
