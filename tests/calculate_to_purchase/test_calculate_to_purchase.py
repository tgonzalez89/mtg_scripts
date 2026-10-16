from __future__ import annotations

from typing import TYPE_CHECKING

from mtg_scripts.calculate_to_purchase import calculate_to_purchase

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_main_preserves_grouped_requirements_and_inventory_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collection = tmp_path / "collection.csv"
    purchased = tmp_path / "purchased.txt"
    collection.write_text("Name,Count\nSol Ring,1\nForest,2\n", encoding="utf-8")
    purchased.write_text("1 Sol Ring\n", encoding="utf-8")
    snapshots = {
        "first": ({"sol ring": 2, "forest": 2}, {"arcane signet": 1}),
        "variant": ({"sol ring": 3, "forest": 1}, {"arcane signet": 2}),
        "extra": ({"sol ring": 1, "island": 2}, {}),
        "allocated": ({"forest": 1}, {}),
    }
    monkeypatch.setattr(calculate_to_purchase, "download_deck", snapshots.__getitem__)
    outputs = [tmp_path / name for name in ("all.txt", "decks.txt", "considering.txt")]
    arguments = [
        "--collection-file",
        str(collection),
        "--purchased-file",
        str(purchased),
        "--want-deck-ids",
        "(first,variant)",
        "extra",
        "--have-deck-ids",
        "allocated",
        "--buy-considering",
        "--to-purchase-file",
        str(outputs[0]),
        "--to-purchase-decks-file",
        str(outputs[1]),
        "--to-purchase-considering-file",
        str(outputs[2]),
    ]
    expected = [
        "1 arcane signet\n1 forest\n2 island\n2 sol ring\n",
        "1 forest\n2 island\n2 sol ring\n",
        "1 arcane signet\n",
    ]
    for _ in range(2):
        assert calculate_to_purchase.main(arguments) == 0
        assert [path.read_text(encoding="utf-8") for path in outputs] == expected


def test_missing_collection_returns_failure(tmp_path: Path) -> None:
    assert (
        calculate_to_purchase.main(["--collection-file", str(tmp_path / "missing.csv"), "--want-deck-ids", "deck"]) == 1
    )
