import re
from urllib.parse import quote, quote_plus

import requests

from print_picker.card_backend import CardBackend

SCRYFALL_SEARCH_URL = "https://api.scryfall.com/cards/search?q="
SCRYFALL_CARD_URL = "https://api.scryfall.com/cards/"
USER_AGENT = "mtg-print-picker/1.0 (contact: local)"


class ScryfallBackend(CardBackend):
    @property
    def user_agent(self):
        return USER_AGENT

    @staticmethod
    def parse_card_line(line):
        quantity_match = re.match(r"^(\d+)\s+(.+)$", line.strip())
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        card_text = quantity_match.group(2).strip() if quantity_match else line.strip()

        foil_match = re.search(r"\s+(\*F\*|\*|★)$", card_text)
        foil_marker = foil_match.group(1) if foil_match else None
        if foil_match:
            card_text = card_text[: foil_match.start()].rstrip()

        set_and_collector_match = re.match(r"^(.+?)\s+\(([A-Za-z0-9]+)\)\s+([A-Za-z0-9][A-Za-z0-9-]*)$", card_text)
        set_match = re.match(r"^(.+?)\s+\(([A-Za-z0-9]+)\)$", card_text)
        collector_match = re.match(r"^(.+?)\s+([0-9][A-Za-z0-9-]*)$", card_text)
        if set_and_collector_match:
            name, set_code, collector_number = set_and_collector_match.groups()
        elif set_match:
            name, set_code = set_match.groups()
            collector_number = None
        elif collector_match:
            name, collector_number = collector_match.groups()
            set_code = None
        else:
            name, set_code, collector_number = card_text, None, None

        hint = {}
        if set_code:
            hint["set"] = set_code
        if collector_number:
            hint["collector_number"] = collector_number
        if foil_marker:
            hint["is_foil"] = True
        item = {"quantity": quantity, "name": name.strip()}
        if hint:
            item["printing_hint"] = hint
        return item

    @staticmethod
    def _normalize_card_name(name):
        return re.sub(r"(?<=\S)\s*/+\s*(?=\S)", " // ", name).strip()

    def search_card(self, name, printing_hint=None):
        normalized_name = self._normalize_card_name(name)
        if printing_hint and printing_hint.get("set") and printing_hint.get("collector_number"):
            return self._search_exact_printing(normalized_name, printing_hint)

        query_parts = [f'!"{normalized_name}"']
        if printing_hint and printing_hint.get("set"):
            query_parts.append(f"set:{printing_hint['set']}")
        url = SCRYFALL_SEARCH_URL + quote_plus(" ".join(query_parts))
        data = self.request_json(url)
        cards = data.get("data", [])
        normalized_name = normalized_name.casefold()
        cards = [card for card in cards if card.get("name", "").casefold() == normalized_name]
        if not printing_hint:
            return cards[0] if cards else None
        return next((card for card in cards if self._matches_printing_hint(card, printing_hint)), None)

    def _search_exact_printing(self, name, printing_hint):
        set_code = quote(str(printing_hint["set"]).lower(), safe="")
        collector_number = quote(str(printing_hint["collector_number"]), safe="")
        try:
            card = self.request_json(f"{SCRYFALL_CARD_URL}{set_code}/{collector_number}")
        except requests.HTTPError:
            return None
        if card.get("name", "").casefold() != name.casefold():
            return None
        if not self._matches_printing_hint(card, printing_hint):
            return None
        return card

    @staticmethod
    def _matches_printing_hint(card, printing_hint):
        if printing_hint.get("set") and card.get("set", "").casefold() != printing_hint["set"].casefold():
            return False
        requested_number = printing_hint.get("collector_number")
        if requested_number:
            actual_number = str(card.get("collector_number", ""))
            if actual_number.casefold() != str(requested_number).casefold():
                return False
        if printing_hint.get("is_foil") is True:
            return "foil" in card.get("finishes", [])
        if printing_hint.get("is_foil") is False:
            return "nonfoil" in card.get("finishes", [])
        return True

    def get_printings(self, oracle_id):
        if not oracle_id:
            return []
        url = SCRYFALL_SEARCH_URL + quote_plus(f"unique:prints oracleid:{oracle_id}")
        printings = []
        while url:
            data = self.request_json(url)
            printings.extend(data.get("data", []))
            url = data.get("next_page") if data.get("has_more") else None
        return printings

    @staticmethod
    def card_sort_fields(card):
        return (
            card.get("name", ""),
            card.get("released_at", ""),
            card.get("set", ""),
            card.get("collector_number", ""),
        )

    @staticmethod
    def printing_display_name(card):
        set_name = card.get("set_name", "")
        set_code = card.get("set", "").upper()
        return f"{set_name} ({set_code}) #{card.get('collector_number', '')}"

    @staticmethod
    def image_url(card, high_quality=False):
        quality = "png" if high_quality else "normal"
        image_uris = card.get("image_uris", {})
        if image_uris.get(quality):
            return image_uris[quality]
        for face in card.get("card_faces") or []:
            face_url = face.get("image_uris", {}).get(quality)
            if face_url:
                return face_url
        return None
