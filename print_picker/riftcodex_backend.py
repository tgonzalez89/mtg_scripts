import re
from urllib.parse import quote_plus

from print_picker.card_backend import CardBackend

RIFTCODEX_SEARCH_URL = "https://api.riftcodex.com/cards/name?exact="
RIFTCODEX_FUZZY_SEARCH_URL = "https://api.riftcodex.com/cards/name?fuzzy="
USER_AGENT = "mtg-print-picker/1.0 (RiftCodex)"


class RiftCodexBackend(CardBackend):
    @property
    def user_agent(self):
        return USER_AGENT

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_release_dates = {}

    def _release_date(self, set_code):
        set_code = str(set_code).casefold()
        if set_code not in self._set_release_dates:
            data = self.request_json(f"https://api.riftcodex.com/sets/set-id/{set_code}")
            self._set_release_dates[set_code] = data.get("published_on", "")
        return self._set_release_dates[set_code]

    @staticmethod
    def parse_card_line(line):
        quantity_match = re.match(r"^(\d+)\s+(.+)$", line.strip())
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        card_text = quantity_match.group(2).strip() if quantity_match else line.strip()
        match = re.match(r"^(.+?)\s+\(([A-Za-z0-9]+-\d+)\)$", card_text)
        if match:
            name, riftbound_id = match.groups()
            return {
                "quantity": quantity,
                "name": name.strip(),
                "printing_hint": {"riftbound_id": riftbound_id.lower()},
            }
        return {"quantity": quantity, "name": card_text}

    def search_card(self, name, printing_hint=None):
        cards = self._search_by_name(name)
        if printing_hint and printing_hint.get("riftbound_id"):
            requested_id = printing_hint["riftbound_id"].casefold()
            card = next(
                (card for card in cards if str(card.get("riftbound_id", "")).casefold().startswith(f"{requested_id}-")),
                None,
            )
        else:
            card = cards[0] if cards else None
        return self._annotate_release_date(card)

    def _annotate_release_date(self, card):
        if card:
            set_info = card.get("set") or {}
            set_code = set_info.get("set_id", "") if isinstance(set_info, dict) else str(set_info)
            card["_release_date"] = self._release_date(set_code)
        return card

    def _search_by_name(self, name):
        normalized_name = re.sub(r"[^a-zA-Z0-9]+", " ", name).strip().lower()
        url = RIFTCODEX_SEARCH_URL + quote_plus(normalized_name)
        data = self.request_json(url)
        return data.get("items", [])

    def _search_by_name_fuzzy(self, name):
        normalized_name = re.sub(r"[^a-zA-Z0-9]+", " ", name).strip().lower()
        url = RIFTCODEX_FUZZY_SEARCH_URL + quote_plus(normalized_name)
        data = self.request_json(url)
        return data.get("items", [])

    def get_printings(self, card_id):
        if not isinstance(card_id, dict):
            return [card_id] if card_id else []

        names = {card_id.get("name", ""), card_id.get("metadata", {}).get("clean_name", "")}
        printings = {}
        exact_candidates = []
        for name in names:
            if not name:
                continue
            exact_candidates.extend(self._search_by_name(name))

        base_names = set()
        for printing in exact_candidates:
            printing_name = printing.get("name", "")
            base_names.add(printing_name.casefold())
            base_names.add(re.sub(r"\s*\([^)]*\)$", "", printing_name).casefold())

        for printing in exact_candidates:
            printings[printing.get("id")] = self._annotate_release_date(printing)
        for name in names:
            if not name:
                continue
            for printing in self._search_by_name_fuzzy(name):
                printing_name = printing.get("name", "").casefold()
                if any(printing_name.startswith(base_name) for base_name in base_names):
                    printings[printing.get("id")] = self._annotate_release_date(printing)
        return list(printings.values())

    def card_sort_fields(self, card):
        set_info = card.get("set") or {}
        set_code = set_info.get("set_id", "") if isinstance(set_info, dict) else str(set_info)
        return (
            card.get("name", ""),
            card.get("_release_date") or self._release_date(set_code),
            set_code,
            card.get("collector_number", ""),
        )

    @staticmethod
    def printing_display_name(card):
        set_info = card.get("set") or {}
        if isinstance(set_info, dict):
            set_label = set_info.get("label", "")
            set_id = set_info.get("set_id", "")
        else:
            set_label = ""
            set_id = str(set_info)
        return f"{set_label} ({set_id.upper()}) #{card.get('collector_number', '')}"

    @staticmethod
    def image_url(card, high_quality=False):
        media = card.get("media") or {}
        if isinstance(media, dict):
            image_url = media.get("image_url")
            if image_url:
                return image_url
        image_url = card.get("image_url")
        return image_url
