import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert Moxfield deck IDs to Forge .dck files"
    )

    parser.add_argument(
        "deck_ids",
        nargs="+",
        help="Moxfield deck IDs to convert",
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help=(
            "Output directory for .dck files (default: %%APPDATA%%/Forge/decks/commander). "
            "Uses forward slashes in output; Windows will handle them correctly."
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


def get_default_output_dir() -> Path:
    """Get the default Forge decks directory."""
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
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
    }
    request = urllib.request.Request(moxfield_api_url + deck_id, headers=headers)
    
    try:
        with urllib.request.urlopen(request) as response:
            if response.status != 200:
                print(f"Failed to get data from Moxfield. Status code: {response.status}")
                return None
            encoding = response.headers.get_content_charset("utf-8")
            data = json.loads(response.read().decode(encoding))
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
    """
    deck_name = data.get("name", "Unnamed Deck")
    
    commanders = {}
    for card_name, card_data in data.get("commanders", {}).items():
        commanders[card_name] = card_data["quantity"]
    
    mainboard = {}
    for card_name, card_data in data.get("mainboard", {}).items():
        mainboard[card_name] = card_data["quantity"]
    
    sideboard = {}
    for card_name, card_data in data.get("sideboard", {}).items():
        sideboard[card_name] = card_data["quantity"]
    
    maybeboard = {}
    for card_name, card_data in data.get("maybeboard", {}).items():
        maybeboard[card_name] = card_data["quantity"]
    
    return deck_name, commanders, mainboard, sideboard, maybeboard


def format_card_list(cards: dict) -> str:
    """
    Format a card dictionary into Forge card list format.
    
    Args:
        cards (dict): Mapping of card names to quantities
        
    Returns:
        str: Formatted card list
    """
    lines = []
    for card_name in sorted(cards.keys()):
        quantity = cards[card_name]
        lines.append(f"{quantity} {card_name}")
    return "\n".join(lines)


def create_dck_file(
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
        bool: True if file was created/overwritten, False if user declined override
    """
    # Check if file exists
    if output_path.exists():
        if not Path(sys.argv[0]).parent:  # Check if --no-override flag was used
            # This is checked via args, handled in main
            pass
    
    # Build file content
    content = "[metadata]\n"
    content += f"name={deck_name}\n"
    
    # Add sections if they have cards
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
    
    # Write file
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w") as f:
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
        output_dir = get_default_output_dir()
    
    print(f"Output directory: {output_dir}")
    
    # Create output directory if it doesn't exist
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error creating output directory {output_dir}: {e}")
        sys.exit(1)
    
    # Process each deck
    successful = 0
    failed = 0
    
    for deck_id in args.deck_ids:
        print(f"\nProcessing deck: {deck_id}")
        
        # Download deck
        data = download_deck(deck_id)
        if not data:
            failed += 1
            continue
        
        # Extract sections
        deck_name, commanders, mainboard, sideboard, maybeboard = extract_deck_sections(data)
        
        # Create filename (replace invalid characters)
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in deck_name)
        safe_name = safe_name.strip()
        output_file = output_dir / f"{safe_name}.dck"
        
        print(f"Deck name: {deck_name}")
        print(f"Output file: {output_file}")
        print(f"  - Mainboard: {len(mainboard)} cards")
        print(f"  - Commanders: {len(commanders)} cards")
        print(f"  - Sideboard: {len(sideboard)} cards")
        
        # Check for existing file
        if output_file.exists() and args.no_override:
            response = input(f"\n{output_file} already exists. Overwrite? (y/n): ").strip().lower()
            if response != "y":
                print("Skipped.")
                continue
        
        # Create file
        if create_dck_file(output_file, deck_name, commanders, mainboard, sideboard):
            print("Created successfully.")
            successful += 1
        else:
            failed += 1
    
    # Summary
    print(f"\n{'='*50}")
    print(f"Summary: {successful} successful, {failed} failed")
    
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
