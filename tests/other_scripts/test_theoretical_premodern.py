from __future__ import annotations

from typing import TYPE_CHECKING, Self, cast

from mtg_scripts.other_scripts import theoretical_premodern
from mtg_scripts.services.scryfall.store import card_from_payload

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from mtg_scripts.services.scryfall import ScryfallService
    from mtg_scripts.services.scryfall.models import ScryfallCard


def _card(name: str, oracle_id: str, set_code: str) -> ScryfallCard:
    return card_from_payload(
        {
            "id": f"{set_code}-{oracle_id}",
            "oracle_id": oracle_id,
            "name": name,
            "set": set_code,
        }
    )


def test_build_lists_deduplicates_oracle_ids_and_does_not_apply_premodern_bans() -> None:
    cards = [
        _card("Already Included", "included", "lea"),
        _card("Already Included", "included", "4ed"),
        _card("Multi-set Addition", "addition", "lea"),
        _card("Multi-set Addition", "addition", "arn"),
        _card("Premodern Banned", "premodern-banned", "atq"),
        _card("Legacy Banned", "legacy-banned", "leg"),
        _card("Vintage Restricted", "restricted", "drk"),
        _card("Legal Addition", "legal", "fem"),
        _card("Badlands", "dual-land", "3ed"),
    ]
    legality_ids = {
        "pauper": set(),
        "legacy": {"legacy-banned"},
        "vintage": set(),
        "restricted_vintage": {"restricted"},
    }

    additions, new_bans, final_pool = theoretical_premodern.build_lists(cards, legality_ids)

    assert [card.name for card in additions] == [
        "Badlands",
        "Legacy Banned",
        "Legal Addition",
        "Multi-set Addition",
        "Premodern Banned",
        "Vintage Restricted",
    ]
    assert [card.oracle_id for card in new_bans] == ["dual-land", "legacy-banned", "restricted"]
    assert [card.oracle_id for card in final_pool] == ["legal", "addition", "premodern-banned"]


def test_manual_ban_names_match_case_insensitively() -> None:
    cards = [_card("badlands", "dual-land", "3ed")]
    legality_ids = {reason: set() for reason, _ in theoretical_premodern.BANNED_QUERIES}

    additions, new_bans, final_pool = theoretical_premodern.build_lists(cards, legality_ids)

    assert [card.oracle_id for card in additions] == ["dual-land"]
    assert [card.oracle_id for card in new_bans] == ["dual-land"]
    assert final_pool == []


def test_enabled_timeline_cards_are_manual_bans() -> None:
    names = (
        "Illusionary Mask",
        "Hymn to Tourach",
        "Stone-Throwing Devils",
        "Berserk",
        "Copy Artifact",
        "Fork",
        "Maze of Ith",
        "High Tide",
        "Sinkhole",
    )
    cards = [_card(name, str(index), "lea") for index, name in enumerate(names)]
    legality_ids = {reason: set() for reason, _ in theoretical_premodern.BANNED_QUERIES}

    _, new_bans, final_pool = theoretical_premodern.build_lists(cards, legality_ids)

    assert {card.name for card in new_bans} == set(names)
    assert final_pool == []


def test_current_pauper_bans_are_filtered() -> None:
    names = ("High Tide", "Hymn to Tourach", "Sinkhole", "Stone-Throwing Devils")
    cards = [_card(name, str(index), "lea") for index, name in enumerate(names)]
    legality_ids = {reason: set() for reason, _ in theoretical_premodern.BANNED_QUERIES}
    legality_ids["pauper"] = {str(index) for index in range(len(names))}

    _, new_bans, final_pool = theoretical_premodern.build_lists(cards, legality_ids)

    assert {card.name for card in new_bans} == set(names)
    assert final_pool == []


def test_fetch_cards_uses_unique_cards_for_all_queries() -> None:
    class FakeResult:
        def __init__(self, cards: tuple[ScryfallCard, ...]) -> None:
            self.cards = cards

    class FakeService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def search(self, query: str, *, unique: str | None = None) -> FakeResult:
            self.calls.append((query, unique))
            oracle_id = f"id-{len(self.calls)}"
            set_code = "4ed" if len(self.calls) == 1 else "lea"
            return FakeResult((_card(oracle_id, oracle_id, set_code),))

    service = FakeService()

    cards, legality = theoretical_premodern.fetch_cards(cast("ScryfallService", service))

    assert len(cards) == 2
    assert service.calls[:2] == [
        (theoretical_premodern.build_set_query(theoretical_premodern.PREMODERN_SETS), "cards"),
        (theoretical_premodern.build_set_query(theoretical_premodern.OLDER_BORDERED_SETS), "cards"),
    ]
    assert service.calls[2:] == [(query, "cards") for _, query in theoretical_premodern.BANNED_QUERIES]
    assert set(legality) == {reason for reason, _ in theoretical_premodern.BANNED_QUERIES}
    assert all(len(query) < 1000 for query, _ in service.calls)


def test_write_report_creates_only_name_lists(tmp_path: Path) -> None:
    report: theoretical_premodern.Report = (
        [_card("Addition", "id-1", "lea")],
        [_card("Removed", "id-2", "lea")],
        [_card("Legal", "id-3", "lea")],
    )

    theoretical_premodern.write_report(tmp_path, report)

    assert {path.name for path in tmp_path.iterdir()} == set(theoretical_premodern.OUTPUT_TEXT_FILENAMES.values())
    bans_text = (tmp_path / theoretical_premodern.OUTPUT_TEXT_FILENAMES["new_bans"]).read_text(encoding="utf-8")
    assert bans_text == "Removed\n"
    assert (tmp_path / theoretical_premodern.OUTPUT_TEXT_FILENAMES["final"]).read_text(encoding="utf-8") == "Legal\n"


def test_main_reports_query_failures_without_writing_outputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class FakeService:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def search(self, query: str, *, unique: str | None = None) -> object:
            class Result:
                cards: tuple[object, ...] = ()

            return Result()

    monkeypatch.setattr(theoretical_premodern, "ScryfallService", FakeService)

    assert theoretical_premodern.main(["--output-dir", str(tmp_path)]) == 1
    assert "no cards for the required legality query" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())
