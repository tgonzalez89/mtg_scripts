"""Feature-local offer payloads shared by scraping, generation, and selection."""

from typing import NotRequired, TypedDict, cast


class OfferRecord(TypedDict):
    total_price: float
    price: float
    shipping_price: float
    amount: int
    seller: str


class ScrapedOffer(OfferRecord):
    condition: str
    language: str
    url: NotRequired[str]


class SelectedOfferRecord(OfferRecord):
    selected_amount: NotRequired[int]
    price_per_card: NotRequired[float]
    card_name: NotRequired[str]
    condition: NotRequired[str]
    language: NotRequired[str]
    url: NotRequired[str]


class SellerAvailability(TypedDict):
    shipping_price: float
    cards_available: int


def to_selected_offer(offer: OfferRecord) -> SelectedOfferRecord:
    """Copy at the mutation boundary, retaining scraper and unknown metadata."""
    return cast("SelectedOfferRecord", dict(offer))
