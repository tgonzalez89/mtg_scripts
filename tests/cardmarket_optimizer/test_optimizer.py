from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mtg_scripts.cardmarket_optimizer import gen_dummy_test_files, models, optimization, optimizer

if TYPE_CHECKING:
    from pathlib import Path


def test_main_preserves_selection_and_has_no_state_between_runs(tmp_path: Path) -> None:
    card_list = tmp_path / "cards.txt"
    sellers = tmp_path / "sellers.json"
    offers = tmp_path / "offers.json"
    output = tmp_path / "selected.json"
    card_list.write_text("2 Sol Ring\n", encoding="utf-8")
    sellers.write_text(json.dumps({"seller": 2.0}), encoding="utf-8")
    offers.write_text(
        json.dumps(
            {"sol ring": [{"total_price": 3.0, "price": 1.0, "shipping_price": 2.0, "amount": 2, "seller": "seller"}]}
        ),
        encoding="utf-8",
    )
    arguments = [
        "--card-list",
        str(card_list),
        "--sellers-database",
        str(sellers),
        "--offers-database",
        str(offers),
        "--selected-offers",
        str(output),
    ]
    assert optimizer.main(arguments) == 0
    first = output.read_text(encoding="utf-8")
    assert optimizer.main(arguments) == 0
    assert output.read_text(encoding="utf-8") == first
    selected = json.loads(first)
    assert selected == {
        "sol ring": [
            {
                "total_price": 3.0,
                "price": 1.0,
                "shipping_price": 2.0,
                "amount": 2,
                "seller": "seller",
                "selected_amount": 2,
                "price_per_card": 2.0,
                "card_name": "sol ring",
            }
        ],
    }
    assert optimization.calc_total_prices(selected) == (4.0, 2.0, 2.0, {"seller"})


def test_offer_tie_breaking_receives_seller_availability_explicitly() -> None:
    offers: list[models.SelectedOfferRecord] = [
        {"total_price": 2.0, "price": 1.0, "shipping_price": 1.0, "amount": 1, "seller": seller}
        for seller in ("small", "large")
    ]
    sellers: dict[str, models.SellerAvailability] = {
        "small": {"shipping_price": 1.0, "cards_available": 1},
        "large": {"shipping_price": 1.0, "cards_available": 5},
    }
    chosen = optimization.get_best_offer(offers, 1, set(), sellers)
    assert chosen is not None
    assert chosen["seller"] == "large"


def test_scraped_offer_adapter_keeps_metadata_and_isolates_selection_mutations() -> None:
    source: models.ScrapedOffer = {
        "total_price": 3.0,
        "price": 1.0,
        "shipping_price": 2.0,
        "amount": 2,
        "seller": "seller",
        "condition": "Near Mint",
        "language": "English",
        "url": "https://example.test/offer",
    }
    selected = models.to_selected_offer(source)
    assert dict(selected) == dict(source)
    selected["selected_amount"] = 2
    assert "selected_amount" not in source
    assert selected["condition"] == "Near Mint"
    assert selected["language"] == "English"
    assert selected["url"] == "https://example.test/offer"


def test_generated_offer_database_remains_consumable_by_optimizer(tmp_path: Path) -> None:
    card_list = tmp_path / "cards.txt"
    sellers = tmp_path / "sellers.json"
    offers = tmp_path / "offers.json"
    output = tmp_path / "selected.json"
    config = gen_dummy_test_files.GenerationConfig(
        num_sellers=1,
        seller_min_shipping_price=2,
        seller_max_shipping_price=2,
        offer_min_price=1,
        offer_max_price=1,
        offer_min_amount=2,
        offer_max_amount=2,
        num_cards=1,
        card_min_offers=1,
        card_max_offers=1,
        buy_list_min_card_amount=2,
        buy_list_max_card_amount=2,
        card_list_path=str(card_list),
        sellers_database_path=str(sellers),
        offers_database_path=str(offers),
    )
    gen_dummy_test_files.generate_data(config)
    source = json.loads(offers.read_text(encoding="utf-8"))
    assert source == {
        "card-name-1": [
            {
                "total_price": 3.0,
                "price": 1.0,
                "shipping_price": 2.0,
                "amount": 2,
                "seller": "seller1",
            }
        ]
    }
    assert card_list.read_text(encoding="utf-8") == "2 card-name-1\n"
    assert (
        optimizer.main(
            [
                "-c",
                str(card_list),
                "-s",
                str(sellers),
                "-o",
                str(offers),
                "-e",
                str(output),
            ]
        )
        == 0
    )
    selected = json.loads(output.read_text(encoding="utf-8"))
    assert selected["card-name-1"][0]["selected_amount"] == 2
    assert optimization.calc_total_prices(selected) == (4.0, 2.0, 2.0, {"seller1"})
    assert json.loads(offers.read_text(encoding="utf-8")) == source
