from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import pytest

from mtg_scripts.calculate_to_purchase import calculate_to_purchase
from mtg_scripts.deck_exporter import deck_exporter
from mtg_scripts.services.moxfield import MoxfieldError, fetch_deck, normalize_moxfield_deck_id

if TYPE_CHECKING:
    from pathlib import Path

    from mtg_scripts.services.moxfield import MoxfieldDeckData


def _deck() -> MoxfieldDeckData:
    return {
        "name": "Fixture",
        "commanders": {"Sol Ring": {"quantity": 1}},
        "mainboard": {
            "Sol Ring": {"quantity": 2, "card": {"layout": "normal", "set": "cmm", "cn": "123"}},
            "Fire // Ice": {"quantity": 1, "card": {"layout": "split", "set": "apc", "cn": "128"}},
        },
        "sideboard": {"Sol Ring": {"quantity": 3}},
        "companions": {"Sol Ring": {"quantity": 4}},
        "maybeboard": {"Arcane Signet": {"quantity": 1}},
    }


class _Response:
    def __init__(self, payload: object, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.closed = False

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error

    def json(self) -> object:
        return self.payload

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("deck-id", "deck-id"),
        (" deck-id ", "deck-id"),
        ("", ""),
        (" / ", ""),
        ("https://moxfield.com/decks/deck-id", "deck-id"),
        ("https://moxfield.com/decks/deck-id/", "deck-id"),
    ],
)
def test_id_normalization_matches_existing_commands(raw: str, expected: str) -> None:
    assert normalize_moxfield_deck_id(raw) == expected


def test_fetch_preserves_optional_and_unknown_fields_without_caching(tmp_path: Path) -> None:
    payload = {"name": "Deck", "mainboard": {"Sol Ring": {"quantity": 1}}, "unknown": {"keep": True}}
    responses: list[_Response] = []
    requested: list[str] = []

    def get(url: str) -> _Response:
        requested.append(url)
        response = _Response(payload)
        responses.append(response)
        return response

    for _ in range(2):
        assert fetch_deck("https://moxfield.com/decks/example/", get=get) is payload
    assert requested == ["https://api.moxfield.com/v2/decks/all/example"] * 2
    assert all(response.closed for response in responses)
    assert not list(tmp_path.iterdir())


def test_http_failure_is_chained_and_response_is_closed() -> None:
    cause = OSError("unavailable")
    response = _Response({}, cause)
    with pytest.raises(MoxfieldError, match="request failed") as raised:
        fetch_deck("deck", get=lambda url: response)
    assert raised.value.__cause__ is cause
    assert response.closed


def test_connection_failure_is_normalized() -> None:
    def get(url: str) -> _Response:
        message = "connection failed"
        raise OSError(message)

    with pytest.raises(MoxfieldError, match="connection failed"):
        fetch_deck("deck", get=get)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"error": "not a deck"},
        {"mainboard": []},
        {"name": 1},
        {"mainboard": {"Card": {}}},
        {"mainboard": {"Card": {"quantity": True}}},
        {"mainboard": {"Card": {"quantity": 1, "card": None}}},
    ],
)
def test_malformed_payload_is_not_an_empty_success(payload: object) -> None:
    response = _Response(payload)
    with pytest.raises(MoxfieldError):
        fetch_deck("deck", get=lambda url: response)
    assert response.closed


def test_empty_id_does_not_call_transport() -> None:
    with pytest.raises(MoxfieldError, match="must not be empty"):
        fetch_deck(" ", get=lambda url: pytest.fail("transport called"))


@pytest.mark.parametrize("transport", ["requests", "curl"])
def test_commands_keep_transport_options_and_own_section_policies(
    monkeypatch: pytest.MonkeyPatch, transport: str
) -> None:
    payload = _deck()
    response = _Response(payload)
    calls: list[tuple[str, dict[str, object]]] = []

    def get(url: str, **kwargs: object) -> _Response:
        calls.append((url, kwargs))
        return response

    if transport == "requests":
        monkeypatch.setattr(calculate_to_purchase.requests, "get", get)
        monkeypatch.setattr(calculate_to_purchase, "DEBUG_JSON", False)
        assert calculate_to_purchase.download_deck("https://moxfield.com/decks/example/") == (
            {"sol ring": 10, "fire // ice": 1},
            {"arcane signet": 1},
        )
    else:
        monkeypatch.setattr(deck_exporter.requests, "get", get)
        monkeypatch.setattr(deck_exporter, "DEBUG", False)
        data = deck_exporter.download_deck("https://moxfield.com/decks/example/")
        assert data is payload
        name, commanders, mainboard, sideboard, maybeboard = deck_exporter.extract_deck_sections(data)
        assert name == "Fixture"
        assert commanders["Sol Ring"]["quantity"] == 1
        assert sideboard["Sol Ring"]["quantity"] == 3
        assert maybeboard["Arcane Signet"]["quantity"] == 1
        assert deck_exporter.format_card_list(mainboard) == "1 Fire // Ice\n2 Sol Ring"
        assert mainboard["Sol Ring"] == {"quantity": 2, "layout": "normal", "set": "cmm", "cn": "123"}
    assert response.closed
    assert len(calls) == 1
    url, options = calls[0]
    assert url == "https://api.moxfield.com/v2/decks/all/example"
    assert options["timeout"] == 30
    if transport == "requests":
        assert options["headers"] == {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        }
        assert "impersonate" not in options
    else:
        assert options["impersonate"] == "chrome"
        assert options["headers"] == {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.moxfield.com",
            "Referer": "https://www.moxfield.com/decks/example",
        }


@pytest.mark.parametrize("transport", ["requests", "curl"])
def test_command_debug_json_keeps_its_formatting_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transport: str
) -> None:
    monkeypatch.chdir(tmp_path)
    payload = _deck()
    response = _Response(payload)
    if transport == "requests":
        monkeypatch.setattr(calculate_to_purchase.requests, "get", lambda url, **kwargs: response)
        monkeypatch.setattr(calculate_to_purchase, "DEBUG_JSON", True)
        calculate_to_purchase.download_deck("example")
        destination = tmp_path / "example.json"
    else:
        monkeypatch.setattr(deck_exporter.requests, "get", lambda url, **kwargs: response)
        monkeypatch.setattr(deck_exporter, "DEBUG", True)
        assert deck_exporter.download_deck("example") == payload
        destination = tmp_path / "debug.json"
    expected = json.dumps(payload, indent=2, sort_keys=transport == "requests").replace("\n", os.linesep)
    assert destination.read_bytes() == expected.encode("utf-8")
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("transport", ["requests", "curl"])
def test_commands_keep_their_http_failure_handling(monkeypatch: pytest.MonkeyPatch, transport: str) -> None:
    if transport == "requests":
        response = _Response({}, calculate_to_purchase.requests.HTTPError("unavailable"))
        monkeypatch.setattr(calculate_to_purchase.requests, "get", lambda url, **kwargs: response)
        with pytest.raises(MoxfieldError, match="unavailable"):
            calculate_to_purchase.download_deck("example")
    else:
        response = _Response({}, deck_exporter.requests.RequestsError("unavailable"))
        monkeypatch.setattr(deck_exporter.requests, "get", lambda url, **kwargs: response)
        assert deck_exporter.download_deck("example") is None
    assert response.closed


def test_malformed_json_is_normalized_and_response_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _Response({})

    def invalid_json() -> object:
        message = "malformed JSON"
        raise ValueError(message)

    monkeypatch.setattr(response, "json", invalid_json)
    with pytest.raises(MoxfieldError, match="Invalid Moxfield JSON"):
        fetch_deck("example", get=lambda url: response)
    assert response.closed


def test_response_close_failure_is_a_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _Response({"name": "Deck"})

    def close() -> None:
        message = "close failed"
        raise OSError(message)

    monkeypatch.setattr(response, "close", close)
    with pytest.raises(MoxfieldError, match="close failed"):
        fetch_deck("example", get=lambda url: response)


def test_exporter_retains_optional_section_and_card_metadata_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _Response({"name": "Partial", "mainboard": {"Sol Ring": {"quantity": 1}}})
    monkeypatch.setattr(deck_exporter.requests, "get", lambda url, **kwargs: response)
    monkeypatch.setattr(deck_exporter, "DEBUG", False)
    data = deck_exporter.download_deck("example")
    assert data is not None
    name, commanders, mainboard, sideboard, maybeboard = deck_exporter.extract_deck_sections(data)
    assert name == "Partial"
    assert commanders == sideboard == maybeboard == {}
    assert mainboard == {"Sol Ring": {"quantity": 1, "layout": "", "set": "", "cn": ""}}
    assert deck_exporter.format_card_list(mainboard) == "1 Sol Ring"
    assert response.closed
