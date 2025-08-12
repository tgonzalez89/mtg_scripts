# python simulator.py $(Get-ChildItem "C:\Users\$env:USERNAME\AppData\Roaming\Forge\decks\commander" -Filter "*.dck" | ForEach-Object { '"{0}"' -f $_.BaseName })


import argparse
import difflib
import re
import time
import tkinter as tk
from itertools import combinations

import cv2
import numpy as np
import pyautogui
import tesserocr
from PIL import Image
from pywinauto import application
from pywinauto.clipboard import GetData
from pywinauto.findwindows import find_window
from pywinauto.keyboard import send_keys
from wakepy import keep

# Config
VERBOSE = True  # Set to True to enable info messages
DEBUG = True  # Set to True to enable debug messages
DEBUG_IMG = True  # Set to True to enable saving debug screenshots.

# Global variables
window = None


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Simulate 4-player free-for-all games in Forge using a list of deck names."
    )
    parser.add_argument("decks", type=str, nargs="+", help="List of deck names (minimum 4).")
    args = parser.parse_args()

    if len(args.decks) < 4:
        raise ValueError(f"You must provide at least 4 deck names. Provided: {args.decks}")

    if DEBUG:
        print(f"Using decks: {args.decks}.")
    return args.decks


def focus_on_window(title_pattern):
    """
    Focus on a window based on a regex pattern that matches any version.

    :param title_pattern: Regex pattern to match the window title.
    :return: True if window is focused, False otherwise.
    """
    global window
    try:
        hwnd = find_window(title_re=title_pattern)
        app = application.Application().connect(handle=hwnd)
        window = app.window(handle=hwnd)
        window.set_focus()
        if DEBUG:
            print(f"Found window: '{window.window_text()}'.")
        time.sleep(0.5)
        return window
    except Exception:
        raise RuntimeError(f"Could not find on a window with pattern {repr(title_pattern)}.")


def alt_tab():
    pyautogui.keyDown("alt")
    time.sleep(pyautogui.MINIMUM_SLEEP)
    pyautogui.press("tab")
    time.sleep(pyautogui.MINIMUM_SLEEP)
    pyautogui.keyUp("alt")
    time.sleep(pyautogui.MINIMUM_SLEEP)


def steal_focus():
    root = tk.Tk()
    root.focus_force()
    root.update()
    root.destroy()


def take_screenshot(second_try=False):
    # steal_focus()
    # time.sleep(pyautogui.MINIMUM_DURATION)
    # window.set_focus()
    # time.sleep(pyautogui.MINIMUM_DURATION)
    pil_screenshot = window.capture_as_image()
    window_rect = window.rectangle()
    client_rect = window.client_rect()
    client_area_rect = window.client_area_rect()
    offset = client_area_rect.left - window_rect.left, client_area_rect.top - window_rect.top
    crop_box = (offset[0], offset[1], client_rect.right + offset[0], client_rect.bottom + offset[1])
    pil_screenshot = pil_screenshot.crop(crop_box)
    if DEBUG_IMG:
        pil_screenshot.save("debug_screenshot.png")
    if np.all(np.array(pil_screenshot.convert("L")) == 0):
        if not second_try:
            if DEBUG:
                "Warning: Black screenshot detected. Trying again."
            return take_screenshot(second_try=True)
        else:
            raise RuntimeError("Bad screenshot! This is an issue with Forge.")
    return pil_screenshot


def find_image_on_screen(image, region=None, screenshot=None, confidence=0.8):
    """
    Search for an image on screen within an optional region.

    :param image: Path to the image file.
    :param region: Region box (left, top, width, height) to limit search area.
    :param screenshot: Image where the image will be searched.
    :param confidence: Match confidence (requires OpenCV).
    :return: Location (left, top, width, height).
    """
    if screenshot is None:
        screenshot = take_screenshot()
    if DEBUG_IMG and region is not None:
        left, top, width, height = region
        right, bottom = left + width, top + height
        screenshot.crop((left, top, right, bottom)).save("debug_find_image_on_screen.png")
    try:
        location = pyautogui.locate(image, screenshot, region=region, confidence=confidence)
        if DEBUG:
            print(f"Image '{image}' found on screen.")
        return location
    except pyautogui.ImageNotFoundException:
        if DEBUG:
            print(f"Image '{image}' not found on screen.")
        return None


def binarize_image(pil_image):
    """
    Convert image to binary using Otsu's method.

    :param pil_image: PIL Image object.
    :return: Binary image suitable for OCR.
    """
    np_gray = np.array(pil_image.convert("L"))
    threshold, np_binary = cv2.threshold(np_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if DEBUG:
        print(f"Darkest pixel: {np.min(np_gray)}, brightest pixel: {np.max(np_gray)}.")
        print(f"Threshold value: {threshold}.")
    if DEBUG_IMG:
        cv2.imwrite("debug_binarize_image_gray.png", np_gray)
        cv2.imwrite("debug_binarize_image_binary.png", np_binary)
    return np_binary


def normalize_text(text):
    # Replace small punctuation with spaces, and collapse multiple spaces.
    # text = re.sub(r"[\-_.,~=]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_text_in_screen(pattern, region=None, screenshot=None, allowlist=None, flags=re.IGNORECASE):
    """
    Search for text on screen within an optional region using EasyOCR.

    :param pattern: The regex pattern to search for.
    :param region: Tuple (left, top, width, height) to limit screenshot area.
    :param screenshot: Image where the text will be searched.
    :param flags: Regex flags.
    :return: The match object if found, otherwise None.
    """
    if screenshot is None:
        screenshot = take_screenshot()
    if region is not None:
        left, top, width, height = region
        right, bottom = left + width, top + height
        screenshot = screenshot.crop((left, top, right, bottom))
    binary_image = binarize_image(screenshot)

    variables = {}
    if allowlist:
        variables["tessedit_char_whitelist"] = allowlist
    with tesserocr.PyTessBaseAPI(
        path=r"C:\Program Files\Tesseract-OCR\tessdata", psm=tesserocr.PSM.SINGLE_LINE, variables=variables
    ) as tess_api:
        tess_api.SetImage(Image.fromarray(binary_image))
        ocr_text = tess_api.GetUTF8Text()
    normalized_ocr = normalize_text(ocr_text)
    match = re.search(pattern, normalized_ocr, flags)
    if match:
        if DEBUG:
            print(f"Pattern {repr(pattern)} found on screen.")
    else:
        if DEBUG:
            print(f"Pattern {repr(pattern)} not found on screen.")
            print(f"OCR result was:\n{repr(normalized_ocr)}")
    return match


def scroll(coords, direction, max_scrolls=5, per_scroll=100):
    """
    Scroll the mouse wheel in the specified direction at the specified coordinates.

    :param coords: Coordinates (x, y) where to scroll.
    :param direction: "up" or "down" to scroll.
    :param max_scrolls: Maximum number of scrolls to perform.
    :param per_scroll: Number of clicks to scroll per action.
    """
    if direction == "up":
        per_scroll = abs(per_scroll)
    elif direction == "down":
        per_scroll = -abs(per_scroll)
    else:
        raise ValueError("Direction must be 'up' or 'down'.")

    client_rect = window.client_area_rect()
    coords = client_rect.left + coords[0], client_rect.top + coords[1]
    pyautogui.moveTo(*coords, duration=pyautogui.MINIMUM_DURATION)
    time.sleep(pyautogui.MINIMUM_SLEEP)
    for _ in range(max_scrolls):
        pyautogui.scroll(per_scroll, *coords)
        time.sleep(pyautogui.MINIMUM_SLEEP)
    time.sleep(pyautogui.MINIMUM_DURATION)


def move_and_click(coords, double_click=False):
    """
    Move the mouse to the specified coordinates and click.

    :param coords: Coordinates (x, y) where to click.
    :param double_click: If True, performs a double click instead of a single click.
    """
    client_rect = window.client_area_rect()
    coords = client_rect.left + coords[0], client_rect.top + coords[1]
    pyautogui.moveTo(*coords, duration=pyautogui.MINIMUM_DURATION)
    time.sleep(pyautogui.MINIMUM_SLEEP)
    if double_click:
        pyautogui.doubleClick(*coords, interval=pyautogui.MINIMUM_SLEEP)
    else:
        pyautogui.click(*coords)
    time.sleep(pyautogui.MINIMUM_SLEEP)


def click_text_box_and_type(coords, text):
    """
    Click on a text box at the specified coordinates, erase the contents, type the given text and press 'enter'.

    :param coords: Coordinates (x, y) where to click.
    :param text: The text to type into the text box.
    """
    move_and_click(coords)
    pyautogui.hotkey("ctrl", "a")  # Select all
    time.sleep(pyautogui.MINIMUM_SLEEP)
    send_keys("{BACKSPACE 1000}", 0)
    time.sleep(pyautogui.MINIMUM_SLEEP)
    pyautogui.write(text, interval=pyautogui.MINIMUM_SLEEP)
    time.sleep(pyautogui.MINIMUM_SLEEP)
    pyautogui.press("enter")
    time.sleep(pyautogui.MINIMUM_SLEEP * 2)


def find_and_click_image(image, region=None, screenshot=None, confidence=0.8):
    """
    Find an image on screen and click it.

    :param expected_image: Path to the image file.
    :param region: Region box (left, top, width, height) to limit search area.
    :param confidence: Match confidence (default = 0.8).
    :return: True if the image was found and clicked, False otherwise.
    """
    location = find_image_on_screen(image, region=region, screenshot=screenshot, confidence=confidence)
    if location:
        move_and_click((location[0] + location[2] // 2, location[1] + location[3] // 2))
        return True
    return False


def ensure_player_is_ai(coords, human_ref_path, ai_ref_path, loc_size=(213, 78), confidence=0.8):
    """
    Use image matching to detect if 'Human' is present. Click to change if found.

    :param coords: Top-left coordinates (x, y) of the switch button.
    :param human_ref_path: Path to the reference image of 'Human' label.
    :param ai_ref_path: Path to the reference image of 'AI' label.
    :param loc_size: Width and height of the region to search.
    :param confidence: Match confidence (default = 0.9).
    """
    x, y = coords
    w, h = loc_size
    region = (x, y, w, h)

    screenshot = take_screenshot()
    human_location = find_image_on_screen(human_ref_path, region, screenshot, confidence)
    ai_location = find_image_on_screen(ai_ref_path, region, screenshot, confidence)

    click_coords = (x + w // 2, y + h // 2)
    if human_location and not ai_location:
        move_and_click(click_coords)

        # Make sure the click was registered.
        # screenshot = take_screenshot()
        # human_location = find_image_on_screen(human_ref_path, region, screenshot, confidence)
        # ai_location = find_image_on_screen(ai_ref_path, region, screenshot, confidence)
        # if human_location or not ai_location:
        #     ValueError("Failed to set player to AI. Human label still found or AI label not found.")

        if DEBUG:
            print("Set player to AI.")
    elif not human_location and ai_location:
        if DEBUG:
            print("Player is already set to AI.")
    else:
        raise ValueError("Unexpected state: both human and AI labels found or neither found.")


def set_player_name(player_name, coords):
    """
    Click on the name field and types in the player name.

    :param name: String name for the player.
    :param coords: Coordinates (x, y) of the textbox location.
    """
    click_text_box_and_type(coords, player_name)

    if DEBUG:
        print(f"Set player name to '{player_name}'.")


def set_player_team(team_number, coords, offset=75):
    """
    Set the team for a player by clicking a dropdown and selecting the option.

    :param team_number: Integer for the team number (1-4).
    :param coords: Coordinates (x, y) of the dropdown location.
    :param offset: Vertical distance (in pixels) between dropdown items.
    """
    if team_number < 1 or team_number > 4:
        raise ValueError("Team number must be between 1 and 4.")

    # Open dropdown.
    move_and_click(coords)
    # Click on the menu item corresponding to the team.
    x, y = coords
    y_offset = y + offset * team_number
    move_and_click((x, y_offset))

    if DEBUG:
        print(f"Set player team to '{team_number}'.")


def globify_strings(strings: list[str]) -> str:
    if len(strings) == 0:
        return ""
    result = strings[0]
    if len(strings) == 1:
        return result
    for string in strings[1:]:
        # Reverse the opcodes so that indexes don't change as the operations are applied.
        for tag, i1, i2, _j1, _j2 in reversed(difflib.SequenceMatcher(None, result, string).get_opcodes()):
            if tag != "equal":
                result = result[:i1] + "*" + result[i2:]
    return result


def find_deck_coordinates(deck_name):
    """
    Searches through visible deck list entries and returns the coordinates of
    the entry that exactly matches `deck_name`.

    :param deck_name: The exact name of the deck to search for.
    :return: (x, y) coordinates of the matching deck, or None if not found.
    """
    x, y = 479, 283
    w, h = 650, 53
    offset = 95
    screenshot = take_screenshot()
    for i in range(8):
        y_offset = y + (i * offset)
        region = (x, y_offset, w, h)
        # Pattern to match deck name exactly.
        pattern = rf"^{re.escape(normalize_text(deck_name))}$"
        if find_text_in_screen(pattern, region, screenshot):
            return (x, y_offset + h)
    return None


def select_deck(deck_name, coords):
    """
    Select a deck from the custom user decks menu.
    """
    if VERBOSE:
        print(f"> Selecting deck '{deck_name}'.")

    # Open the deck selection screen.
    move_and_click(coords)
    # Open the 'Custom User Decks' decks.
    deck_type_coords = (1155, 120)
    move_and_click(deck_type_coords)
    custom_user_decks_coords = (1155, 188)
    move_and_click(custom_user_decks_coords)
    # Search for the deck.
    search_box_coords = (409, 188)
    click_text_box_and_type(search_box_coords, f'"{deck_name}"')
    # Select the deck.
    deck_coords = find_deck_coordinates(deck_name)
    if not deck_coords:
        raise ValueError(f"Deck '{deck_name}' not found in the list.")
    move_and_click(deck_coords, double_click=True)


def setup_player(player_number, base_coords):
    """
    Set up a Forge AI player given a base coordinate.

    :param player_number: Player index (1 to 4).
    :param base_coords: Top-left corner (x, y) of the player row.
    """
    if VERBOSE:
        print(f"> Doing setup for player number {player_number}.")

    if player_number < 1 or player_number > 4:
        raise ValueError("Player number must be between 1 and 4.")

    type_offset = (1005, 75)
    name_offset = (311, 34)
    team_offset = (975, 112)

    x, y = base_coords
    coords_type = (x + type_offset[0], y + type_offset[1])
    coords_name = (x + name_offset[0], y + name_offset[1])
    coords_team = (x + team_offset[0], y + team_offset[1])

    ensure_player_is_ai(coords_type, "human.png", "ai.png")
    set_player_name(str(player_number), coords_name)
    set_player_team(player_number, coords_team)


def main():
    focus_on_window(r"Forge.*SNAPSHOT.*")

    all_decks = parse_arguments()

    match_setup_loc = (375, 0, 1537, 82)
    if find_image_on_screen("match_setup.png", match_setup_loc) is None:
        raise RuntimeError("Forge is not in the correct mode. Setup a commander 4-player match.")

    # Setup players.
    player_1_coords = (386, 94)
    player_2_coords = (386, 345)
    player_3_coords = (386, 379)
    player_4_coords = (386, 634)
    scroll(player_1_coords, "up")
    setup_player(1, player_1_coords)
    setup_player(2, player_2_coords)
    scroll(player_1_coords, "down")
    setup_player(3, player_3_coords)
    setup_player(4, player_4_coords)

    deck_combinations = list(combinations(all_decks, 4))
    match_counts = {deck: 0 for deck in all_decks}
    match_wins = {deck: 0 for deck in all_decks}
    game_counts = {deck: 0 for deck in all_decks}
    game_wins = {deck: 0 for deck in all_decks}
    deck_offset = (589, 195)
    for match_idx, decks in enumerate(deck_combinations):
        # Setup the match.
        print(f">> Setting up match {match_idx + 1}/{len(deck_combinations)} with decks: {decks}.")
        scroll(player_1_coords, "up")
        select_deck(decks[0], (player_1_coords[0] + deck_offset[0], player_1_coords[1] + deck_offset[1]))
        select_deck(decks[1], (player_2_coords[0] + deck_offset[0], player_2_coords[1] + deck_offset[1]))
        scroll(player_1_coords, "down")
        select_deck(decks[2], (player_3_coords[0] + deck_offset[0], player_3_coords[1] + deck_offset[1]))
        select_deck(decks[3], (player_4_coords[0] + deck_offset[0], player_4_coords[1] + deck_offset[1]))

        # Start the match.
        print(">> Starting the match.")
        start_button_coords = (997, 975)
        move_and_click(start_button_coords)

        # Wait for the match to end.
        print(">> Waiting for the match to end.")
        window_width, window_height = window.client_rect().right, window.client_rect().bottom
        quit_match_button_loc = (510, 540, 892, 109)
        game_counter = 0
        while True:
            screenshot = take_screenshot()
            # Check if match has ended.
            if find_image_on_screen("quit_match.png", quit_match_button_loc, screenshot) is None:
                # Match is still ongoing, check if a new game has started. Also speed up the game.
                ten_x_speed_button_loc = (window_width - 115, window_height - 115, window_width, window_height)
                if find_and_click_image("10x_speed.png", ten_x_speed_button_loc, screenshot):
                    game_counter += 1
                    print(f">> Game {game_counter} has started.")
                    pyautogui.moveTo(10, 10, duration=pyautogui.MINIMUM_DURATION)
            else:
                # Match has ended.
                # Find how many games won each player and who won the match.
                if not find_and_click_image("copy_to_clipboard.png", (475, 985, 965, 75), screenshot):
                    raise RuntimeError("Couldn't copy log to clipboard.")
                re_match = re.match(
                    r"^Match result: 1: ([0-3]) 2: ([0-3]) 3: ([0-3]) 4: ([0-3])\s*$",
                    GetData().split("\n", maxsplit=1)[0],
                )
                if re_match:
                    winner_idx = -1
                    winner_games_won = -1
                    for player_idx in range(4):
                        game_counts[decks[player_idx]] += game_counter
                        games_won = int(re_match.group(player_idx + 1))
                        game_wins[decks[player_idx]] += games_won
                        if VERBOSE:
                            print(f"> '{decks[player_idx]}' won {games_won} games.")
                        if games_won > winner_games_won:
                            winner_idx = player_idx
                            winner_games_won = games_won
                        match_counts[decks[player_idx]] += 1
                    match_wins[decks[winner_idx]] += 1
                    print(f">> Match {match_idx + 1} ended after {game_counter} games. Winner: '{decks[winner_idx]}'.")
                    find_and_click_image("quit_match.png", quit_match_button_loc, screenshot)
                    break
                else:
                    raise RuntimeError("Couldn't parse the match summary.")
            time.sleep(5)

    for deck, wins in sorted(match_wins.items(), key=lambda item: item[1], reverse=True):
        print(f">> Deck '{deck}' won {wins} matches. Match win rate: {100 * wins / match_counts[deck]}%.")
        print(
            f">> Deck '{deck}' won {game_wins[deck]} games. Game win rate: {100 * game_wins[deck] / game_counts[deck]}%."
        )


if __name__ == "__main__":
    try:
        with keep.presenting():
            main()
        if DEBUG:
            alt_tab()
    except Exception as e:
        if DEBUG and "Could not find on a window with pattern" not in str(e):
            alt_tab()
        raise
