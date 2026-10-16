"""Moxfield deck fetching with an injected HTTP transport and no persistent cache."""

from __future__ import annotations

from contextlib import closing
from typing import TYPE_CHECKING, Final, NotRequired, Protocol, TypedDict, TypeIs, cast

if TYPE_CHECKING:
    from collections.abc import Callable

MOXFIELD_API_URL: Final = "https://api.moxfield.com/v2/decks/all/"
DECK_SECTIONS: Final = ("commanders", "mainboard", "sideboard", "companions", "maybeboard")


class MoxfieldCardInfo(TypedDict, total=False):
    layout: str
    set: str
    cn: str


class MoxfieldCardEntry(TypedDict):
    quantity: int
    card: NotRequired[MoxfieldCardInfo]


class MoxfieldDeckData(TypedDict, total=False):
    name: str
    commanders: dict[str, MoxfieldCardEntry]
    mainboard: dict[str, MoxfieldCardEntry]
    sideboard: dict[str, MoxfieldCardEntry]
    companions: dict[str, MoxfieldCardEntry]
    maybeboard: dict[str, MoxfieldCardEntry]


class MoxfieldError(RuntimeError):
    """A deck request failed or returned an invalid provider payload."""


class MoxfieldResponse(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> object: ...

    def close(self) -> None: ...


def normalize_moxfield_deck_id(deck_id: str) -> str:
    cleaned = deck_id.strip().rstrip("/")
    return cleaned.rsplit("/", 1)[-1] if "/" in cleaned else cleaned


def _json_object(payload: object, label: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        message = f"Invalid Moxfield object: {label}"
        raise MoxfieldError(message)
    if not _is_string_keyed_object(payload):
        message = f"Invalid Moxfield object keys: {label}"
        raise MoxfieldError(message)
    return payload


def _is_string_keyed_object(value: object) -> TypeIs[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _parse_deck(payload: object) -> MoxfieldDeckData:
    deck = _json_object(payload, "deck")
    if not any(field in deck for field in ("name", *DECK_SECTIONS)):
        message = "Moxfield response has no deck fields."
        raise MoxfieldError(message)
    if "name" in deck and not isinstance(deck["name"], str):
        message = "Moxfield deck name must be a string when provided."
        raise MoxfieldError(message)
    for section in DECK_SECTIONS:
        entries = _json_object(deck.get(section, {}), section)
        for name, raw_entry in entries.items():
            entry = _json_object(raw_entry, f"{section}: {name}")
            quantity = entry.get("quantity")
            if not isinstance(quantity, int) or isinstance(quantity, bool):
                message = f"Invalid Moxfield card entry in {section}: {name}"
                raise MoxfieldError(message)
            card = _json_object(entry.get("card", {}), f"card details: {name}")
            if any(field in card and not isinstance(card[field], str) for field in ("layout", "set", "cn")):
                message = f"Invalid Moxfield card details in {section}: {name}"
                raise MoxfieldError(message)
    return cast("MoxfieldDeckData", deck)


def fetch_deck(
    deck_id: str,
    *,
    get: Callable[[str], MoxfieldResponse],
    transport_errors: tuple[type[Exception], ...] = (OSError,),
) -> MoxfieldDeckData:
    normalized_id = normalize_moxfield_deck_id(deck_id)
    if not normalized_id:
        message = "Moxfield deck ID must not be empty."
        raise MoxfieldError(message)
    try:
        with closing(get(MOXFIELD_API_URL + normalized_id)) as response:
            response.raise_for_status()
            return _parse_deck(response.json())
    except transport_errors as error:
        message = f"Moxfield request failed for {normalized_id}: {error}"
        raise MoxfieldError(message) from error
    except ValueError as error:
        message = f"Invalid Moxfield JSON for {normalized_id}: {error}"
        raise MoxfieldError(message) from error
