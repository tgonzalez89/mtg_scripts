from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

import pytest

from mtg_scripts.print_picker import scryfall_store
from mtg_scripts.print_picker.models import CardPrint, PrintQuery
from mtg_scripts.print_picker.scryfall_backend import ScryfallBackend
from mtg_scripts.print_picker.scryfall_store import CardStore

if TYPE_CHECKING:
    from pathlib import Path

ORACLE_URI = "https://data.scryfall.io/oracle-cards/oracle-v1.jsonl.gz"
DEFAULT_URI = "https://data.scryfall.io/default-cards/default-v1.jsonl.gz"


def _card(**overrides: object) -> dict[str, Any]:
    card: dict[str, Any] = {
        "name": "Llanowar Elves",
        "set": "m12",
        "set_name": "Magic 2012",
        "collector_number": "1",
        "finishes": ["nonfoil"],
        "oracle_id": "oracle-llanowar",
        "released_at": "2011-07-15",
        "set_type": "core",
        "games": ["paper"],
        "image_uris": {"normal": "n.png", "png": "hq.png"},
    }
    card.update(overrides)
    return card


def _backend(tmp_path: Path, cards: list[dict[str, Any]]) -> ScryfallBackend:
    """Build a backend whose store is prebuilt from `cards`, with no network."""
    backend = ScryfallBackend(cache_dir=tmp_path)
    metadata = {
        "oracle_cards": {"jsonl_download_uri": ORACLE_URI},
        "default_cards": {"jsonl_download_uri": DEFAULT_URI},
    }
    (backend.bulk_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    version = backend._cache_name(f"{ORACLE_URI}\n{DEFAULT_URI}")[:16]
    scryfall_store.build_from_cards(scryfall_store.store_path(backend.bulk_dir, version), cards)
    return backend


def _resolve(backend: ScryfallBackend, line: str) -> CardPrint | None:
    return backend.resolve([ScryfallBackend.parse_line(line)])[0].card


def _resolved(backend: ScryfallBackend, line: str) -> CardPrint:
    """Resolve a line that is expected to match exactly one printing."""
    card = _resolve(backend, line)
    assert card is not None, line
    return card


# ---------------------------------------------------------------------------
# Import parsing
# ---------------------------------------------------------------------------


def test_parse_all_printing_hint_combinations() -> None:
    cases = {
        "1 Llanowar Elves": PrintQuery(),
        "1 Llanowar Elves 3": PrintQuery(collector_number="3"),
        "1 Llanowar Elves *F*": PrintQuery(foil=True),
        "1 Llanowar Elves 3 *F*": PrintQuery(collector_number="3", foil=True),
        "1 Llanowar Elves (m12)": PrintQuery(set_code="m12"),
        "1 Llanowar Elves (m12) *F*": PrintQuery(set_code="m12", foil=True),
        "1 Llanowar Elves (m12) 182": PrintQuery(set_code="m12", collector_number="182"),
        "1 Llanowar Elves (m12) 182 *F*": PrintQuery(set_code="m12", collector_number="182", foil=True),
    }
    for line, expected in cases.items():
        assert ScryfallBackend.parse_line(line).query == expected, line


def test_parse_quantity_and_name() -> None:
    entry = ScryfallBackend.parse_line("13 Forest")
    assert entry.quantity == 13
    assert entry.name == "Forest"
    assert not entry.query


def test_unquantified_line_defaults_to_one_copy() -> None:
    assert ScryfallBackend.parse_line("Sol Ring").quantity == 1


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def test_printing_hints_filter_set_number_and_finish(tmp_path: Path) -> None:
    # Distinct release dates so each expectation below follows from the stated
    # rules (newest match, nonfoil unless foil is asked for) rather than from
    # the order the fixtures happen to be stored in.
    cards = [
        _card(id="m12", set="m12", collector_number="182", finishes=["nonfoil", "foil"], released_at="2011-07-15"),
        _card(id="set", set="abc", collector_number="3", finishes=["nonfoil"], released_at="2009-01-01"),
        _card(id="foil", set="abc", collector_number="3★", finishes=["foil"], released_at="2008-01-01"),
    ]
    backend = _backend(tmp_path, cards)
    cases = {
        "1 Llanowar Elves": "m12",
        "1 Llanowar Elves 3": "set",
        "1 Llanowar Elves *F*": "m12",
        "1 Llanowar Elves 3 *F*": "foil",
        "1 Llanowar Elves (m12)": "m12",
        "1 Llanowar Elves (m12) *F*": "m12",
        "1 Llanowar Elves (m12) 182": "m12",
        "1 Llanowar Elves (m12) 182 *F*": "m12",
    }
    for line, expected_id in cases.items():
        card = _resolve(backend, line)
        assert card is not None, line
        assert card.print_id == expected_id, line


def test_collector_numbers_are_exact_without_foil_hint(tmp_path: Path) -> None:
    cards = [
        _card(id="m12-182", set="m12", collector_number="182", finishes=["nonfoil", "foil"]),
        _card(id="pdmu-1-foil", set="pdmu", collector_number="1★", finishes=["foil"]),
        _card(id="7ed-231", set="7ed", collector_number="231", finishes=["nonfoil"]),
        _card(id="7ed-231-foil", set="7ed", collector_number="231★", finishes=["foil"]),
    ]
    backend = _backend(tmp_path, cards)

    assert _resolved(backend, "1 Llanowar Elves 1").print_id == "pdmu-1-foil"
    assert _resolved(backend, "1 Llanowar Elves 1 *F*").print_id == "pdmu-1-foil"
    # A collector number is matched exactly; "18" must not fuzzily hit "182".
    assert _resolve(backend, "1 Llanowar Elves 18") is None
    assert _resolve(backend, "1 Llanowar Elves 23 *F*") is None
    assert _resolved(backend, "1 Llanowar Elves 231").print_id == "7ed-231"


def test_explicit_nonfoil_hint_selects_nonfoil_printing(tmp_path: Path) -> None:
    cards = [
        _card(id="7ed-231", set="7ed", collector_number="231", finishes=["nonfoil"]),
        _card(id="7ed-231-foil", set="7ed", collector_number="231★", finishes=["foil"]),
    ]
    backend = _backend(tmp_path, cards)
    entry = ScryfallBackend.parse_line("1 Llanowar Elves 231")
    nonfoil_entry = type(entry)(
        quantity=entry.quantity, name=entry.name, query=PrintQuery(collector_number="231", foil=False)
    )
    resolved = backend.resolve([nonfoil_entry])[0].card
    assert resolved is not None
    assert resolved.print_id == "7ed-231"


def test_set_only_foil_hint_uses_shared_finish_record(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="fdc-213", set="fdc", collector_number="213", finishes=["nonfoil", "foil"])])
    for line in ("1 Llanowar Elves (FDC)", "1 Llanowar Elves (FDC) *F*"):
        card = _resolve(backend, line)
        assert card is not None, line
        assert card.print_id == "fdc-213", line


def test_unknown_card_resolves_to_none_without_error(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="m12")])
    resolution = backend.resolve([ScryfallBackend.parse_line("1 Not A Real Card")])[0]
    assert resolution.card is None
    assert resolution.error is None


def test_real_cards_are_preferred_over_tokens(tmp_path: Path) -> None:
    cards = [
        _card(id="token", set="tm12", layout="token", oracle_id="oracle-token"),
        _card(id="real", set="m12"),
    ]
    backend = _backend(tmp_path, cards)
    card = _resolve(backend, "1 Llanowar Elves")
    assert card is not None
    assert card.print_id == "real"


def test_memorabilia_is_not_preferred_over_a_playable_card(tmp_path: Path) -> None:
    """Art Series cards live in `memorabilia` sets and match by front-face name."""
    cards = [
        _card(
            id="real",
            name="Forest",
            set="trk",
            collector_number="325",
            oracle_id="o-forest",
            set_type="expansion",
            released_at="2020-01-01",
        ),
        {
            # Newer than the real card, so only the demotion can keep it from winning.
            "id": "art",
            "name": "Forest // Forest",
            "set": "amsh",
            "set_name": "Art Series",
            "set_type": "memorabilia",
            "collector_number": "17",
            "finishes": ["nonfoil"],
            "oracle_id": "o-forest-art",
            "released_at": "2026-06-26",
            "card_faces": [
                {"name": "Forest", "image_uris": {"normal": "a.png"}},
                {"name": "Forest", "image_uris": {"normal": "b.png"}},
            ],
        },
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Forest").print_id == "real"


def test_token_set_type_is_demoted_like_a_token_layout(tmp_path: Path) -> None:
    cards = [
        _card(id="token-set", set="ttsr", set_type="token", oracle_id="o-tok", released_at="2026-01-01"),
        _card(id="real", set="fdn", set_type="core", released_at="2011-01-01"),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Llanowar Elves").print_id == "real"


def test_memorabilia_still_resolves_when_it_is_the_only_option(tmp_path: Path) -> None:
    """Demoting must rank printings, never discard the only one available."""
    backend = _backend(tmp_path, [_card(id="art-only", set="amsh", set_type="memorabilia")])
    assert _resolved(backend, "1 Llanowar Elves").print_id == "art-only"


def test_an_explicit_request_for_memorabilia_is_honoured(tmp_path: Path) -> None:
    """Demotion breaks ties; it must not override a set the user asked for."""
    cards = [
        _card(id="real", set="fdn", set_type="core"),
        _card(id="art", set="amsh", set_type="memorabilia", collector_number="17"),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Llanowar Elves (amsh)").print_id == "art"


def test_paper_printings_are_preferred_over_digital_only_ones(tmp_path: Path) -> None:
    """An MTGO-only promo must not beat the real paper card it reprints."""
    cards = [
        # Newer and otherwise identical, so only the paper rule can demote it.
        _card(id="mtgo", set="prm", set_type="promo", games=["mtgo"], released_at="2026-01-01"),
        _card(id="paper", set="iko", set_type="expansion", games=["arena", "mtgo", "paper"], released_at="2020-04-24"),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Llanowar Elves").print_id == "paper"


def test_digital_only_printings_still_resolve_when_alone(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="mtgo-only", set="vma", games=["mtgo"])])
    assert _resolved(backend, "1 Llanowar Elves").print_id == "mtgo-only"


def test_unknown_platforms_count_as_digital(tmp_path: Path) -> None:
    """Scryfall also lists `astral` and `sega`; neither is something you can print."""
    cards = [
        _card(id="sega", set="sega", games=["sega"], released_at="2026-01-01"),
        _card(id="paper", set="fdn", games=["paper"], released_at="2000-01-01"),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Llanowar Elves").print_id == "paper"


def test_being_a_deck_card_outranks_being_paper(tmp_path: Path) -> None:
    """A real card wins even when the collectible is the only paper printing."""
    cards = [
        _card(id="art", set="amsh", set_type="memorabilia", games=["paper"], released_at="2026-01-01"),
        _card(id="real", set="vma", set_type="masters", games=["mtgo"], released_at="2014-01-01"),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Llanowar Elves").print_id == "real"


@pytest.mark.parametrize("set_type", ["memorabilia", "token", "minigame", "vanguard"])
def test_every_nonplayable_set_type_is_demoted(tmp_path: Path, set_type: str) -> None:
    cards = [
        _card(id="odd", set="odd", set_type=set_type, released_at="2026-01-01"),
        _card(id="real", set="fdn", set_type="core", released_at="2000-01-01"),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Llanowar Elves").print_id == "real"


def test_a_name_ending_in_a_number_is_tried_as_a_whole_name(tmp_path: Path) -> None:
    """`Specimen 73` parses as "Specimen" #73, but is also a card name itself."""
    cards = [_card(id="specimen", name="Specimen 73", set="pip", collector_number="878", oracle_id="o-spec")]
    backend = _backend(tmp_path, cards)
    resolution = backend.resolve([ScryfallBackend.parse_line("1 Specimen 73")])[0]
    assert resolution.card is not None
    assert resolution.card.print_id == "specimen"
    # The retried reading replaces the entry, so the line exports correctly.
    assert resolution.entry.name == "Specimen 73"
    assert ScryfallBackend.export_card_text(resolution.card, resolution.entry) == "Specimen 73 (pip) 878"


def test_the_collector_number_reading_still_wins_when_it_matches(tmp_path: Path) -> None:
    """The fallback must only apply when the first reading found nothing."""
    cards = [
        _card(id="numbered", name="Llanowar Elves", set="m12", collector_number="182"),
        _card(id="oddly-named", name="Llanowar Elves 182", set="xyz", collector_number="1", oracle_id="o-odd"),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Llanowar Elves 182").print_id == "numbered"


def test_a_failed_number_reading_does_not_invent_a_match(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="m12", set="m12", collector_number="182")])
    assert _resolve(backend, "1 Llanowar Elves 18") is None


def test_resolve_preserves_input_order(tmp_path: Path) -> None:
    cards = [
        _card(id="elves", name="Llanowar Elves", oracle_id="o-elves"),
        _card(id="ring", name="Sol Ring", oracle_id="o-ring"),
    ]
    backend = _backend(tmp_path, cards)
    entries = [ScryfallBackend.parse_line(line) for line in ("1 Sol Ring", "1 Llanowar Elves")]
    resolutions = backend.resolve(entries)
    assert [resolution.card.print_id for resolution in resolutions if resolution.card] == ["ring", "elves"]
    assert [resolution.entry.name for resolution in resolutions] == ["Sol Ring", "Llanowar Elves"]


def test_resolve_of_empty_deck_is_empty(tmp_path: Path) -> None:
    assert _backend(tmp_path, [_card(id="m12")]).resolve([]) == []


# ---------------------------------------------------------------------------
# Names, faces and printings
# ---------------------------------------------------------------------------


def test_double_faced_card_is_found_by_front_face_name(tmp_path: Path) -> None:
    dfc = {
        "id": "isd-51",
        "name": "Delver of Secrets // Insectile Aberration",
        "set": "isd",
        "set_name": "Innistrad",
        "collector_number": "51",
        "finishes": ["nonfoil"],
        "oracle_id": "oracle-delver",
        "released_at": "2011-09-30",
        "card_faces": [
            {"name": "Delver of Secrets", "image_uris": {"normal": "f1.png", "png": "f1hq.png"}},
            {"name": "Insectile Aberration", "image_uris": {"normal": "f2.png", "png": "f2hq.png"}},
        ],
    }
    backend = _backend(tmp_path, [dfc])
    card = _resolve(backend, "1 Delver of Secrets")
    assert card is not None
    assert card.print_id == "isd-51"
    assert [face.name for face in card.faces] == ["Delver of Secrets", "Insectile Aberration"]
    assert card.image_urls() == ("f1.png", "f2.png")
    assert card.image_urls(high_quality=True) == ("f1hq.png", "f2hq.png")


def test_unhinted_line_prefers_a_nonfoil_printing(tmp_path: Path) -> None:
    cards = [
        _card(id="foil-only", set="abc", collector_number="3", finishes=["foil"]),
        _card(id="nonfoil", set="m12", collector_number="182", finishes=["nonfoil", "foil"]),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Llanowar Elves").print_id == "nonfoil"
    # An explicit foil request still reaches the foil-only printing.
    assert _resolved(backend, "1 Llanowar Elves 3 *F*").print_id == "foil-only"


def test_exact_name_outranks_a_front_face_match(tmp_path: Path) -> None:
    """A plain "Forest" must not resolve to the double-faced "Forest // Forest"."""
    cards = [
        _card(id="basic", name="Forest", set="trk", collector_number="325", oracle_id="o-forest"),
        {
            "id": "dfc",
            "name": "Forest // Forest",
            "set": "amsh",
            "set_name": "Double Feature",
            "collector_number": "17",
            "finishes": ["nonfoil"],
            "oracle_id": "o-forest-dfc",
            "released_at": "2025-01-01",
            "card_faces": [
                {"name": "Forest", "image_uris": {"normal": "a.png"}},
                {"name": "Forest", "image_uris": {"normal": "b.png"}},
            ],
        },
    ]
    backend = _backend(tmp_path, cards)
    card = _resolved(backend, "1 Forest")
    assert card.print_id == "basic"
    # The double-faced card is still reachable by its full name.
    assert _resolved(backend, "1 Forest // Forest").print_id == "dfc"


def test_newest_printing_wins_among_equal_matches(tmp_path: Path) -> None:
    cards = [
        _card(id="old", set="m12", collector_number="182", released_at="2011-07-15"),
        _card(id="new", set="fdn", collector_number="227", released_at="2024-11-15"),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Llanowar Elves").print_id == "new"


def test_slash_separated_name_is_normalized(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="x", name="Fire // Ice", oracle_id="o-fire")])
    assert _resolve(backend, "1 Fire/Ice") is not None
    assert _resolve(backend, "1 Fire // Ice") is not None


def test_flavor_name_resolves_to_the_printing_that_bears_it(tmp_path: Path) -> None:
    """Naming an alternate-art card must give that card, not the plain reprint."""
    cards = [
        # The flavor-named printing is not Scryfall's default for this oracle id.
        _card(id="alias", name="Llanowar Elves", flavor_name="Galadhrim Bowman", set="ltr", collector_number="9"),
        _card(id="plain", name="Llanowar Elves", set="m12", collector_number="182", released_at="2026-01-01"),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Galadhrim Bowman").print_id == "alias"
    # The real name still resolves to the ordinary printing.
    assert _resolved(backend, "1 Llanowar Elves").print_id == "plain"


def test_a_real_card_name_outranks_another_card_flavor_name(tmp_path: Path) -> None:
    """A direct name match beats a flavor name that happens to collide."""
    cards = [
        _card(id="real", name="Shock", oracle_id="o-shock", set="m21", released_at="2000-01-01"),
        _card(
            id="flavored",
            name="Lightning Bolt",
            flavor_name="Shock",
            oracle_id="o-bolt",
            set="sld",
            released_at="2026-01-01",
        ),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Shock").print_id == "real"


def test_flavor_named_printing_wins_even_when_older(tmp_path: Path) -> None:
    """Match directness decides, not the release date tiebreak."""
    cards = [
        _card(id="alias", name="Llanowar Elves", flavor_name="Galadhrim Bowman", set="ltr", released_at="2000-01-01"),
        _card(id="plain", name="Llanowar Elves", set="m12", released_at="2026-01-01"),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Galadhrim Bowman").print_id == "alias"


def test_a_set_hint_is_applied_to_flavor_name_matches(tmp_path: Path) -> None:
    """A flavor name plus a set narrows within the printings bearing that name."""
    cards = [
        _card(id="alias", name="Llanowar Elves", flavor_name="Galadhrim Bowman", set="ltr", collector_number="9"),
        _card(id="plain", name="Llanowar Elves", set="m12", collector_number="182"),
    ]
    backend = _backend(tmp_path, cards)
    assert _resolved(backend, "1 Galadhrim Bowman (ltr) 9").print_id == "alias"
    # A set the flavor name was never printed in is a contradiction, not a
    # reason to fall back to some unrelated printing.
    assert _resolve(backend, "1 Galadhrim Bowman (m12) 182") is None


def test_printings_of_returns_every_printing_sharing_an_oracle_key(tmp_path: Path) -> None:
    cards = [
        _card(id="a", set="m12", collector_number="182"),
        _card(id="b", set="7ed", collector_number="231"),
        _card(id="other", name="Sol Ring", oracle_id="oracle-sol"),
    ]
    backend = _backend(tmp_path, cards)
    card = _resolve(backend, "1 Llanowar Elves")
    assert card is not None
    assert {printing.print_id for printing in backend.printings_of(card)} == {"a", "b"}


# ---------------------------------------------------------------------------
# Store behaviour
# ---------------------------------------------------------------------------


def test_store_is_reused_across_backend_instances(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="cached")])
    assert _resolved(backend, "1 Llanowar Elves").print_id == "cached"

    # A second backend over the same cache must not need to rebuild: the bulk
    # source files were never written, so any rebuild attempt would fail.
    reopened = ScryfallBackend(cache_dir=tmp_path)
    assert _resolved(reopened, "1 Llanowar Elves").print_id == "cached"
    reopened.close()
    backend.close()


def test_store_rejects_writes(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="m12")])
    store = backend._card_store()
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        store._connection.execute("DELETE FROM prints")
    backend.close()


def test_closing_the_backend_releases_the_store(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="m12")])
    assert _resolve(backend, "1 Llanowar Elves") is not None
    assert backend._store is not None
    backend.close()
    assert backend._store is None


def test_superseded_artifacts_are_discarded(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="m12")])
    legacy_pickle = backend.bulk_dir / "cards-deadbeef-v2.pickle"
    legacy_pickle.write_bytes(b"obsolete")
    stale_store = backend.bulk_dir / "cards-deadbeef-v3.db"
    stale_store.write_bytes(b"obsolete")
    bulk_source = backend.bulk_dir / "default_cards-deadbeef.jsonl.gz"
    bulk_source.write_bytes(b"obsolete")

    store = backend._card_store()

    assert not legacy_pickle.exists()
    assert not stale_store.exists()
    # The store supersedes the compressed sources it was built from.
    assert not bulk_source.exists()
    assert store.path.exists()
    backend.close()


def test_store_round_trips_every_field(tmp_path: Path) -> None:
    card = _card(
        id="round-trip",
        set="fdc",
        set_name="Foundations",
        collector_number="213",
        finishes=["nonfoil", "foil"],
        released_at="2024-11-15",
    )
    path = tmp_path / "cards.db"
    scryfall_store.build_from_cards(path, [card])
    store = CardStore(path)
    [match] = store.by_name(["Llanowar Elves"])["llanowar elves"]
    stored = match.card
    assert stored.print_id == "round-trip"
    assert stored.name == "Llanowar Elves"
    assert stored.set_code == "fdc"
    assert stored.set_name == "Foundations"
    assert stored.collector_number == "213"
    assert stored.released_on == "2024-11-15"
    assert stored.finishes == frozenset({"nonfoil", "foil"})
    assert stored.is_default_print is True
    assert stored.is_token is False
    assert stored.backend == "scryfall"
    store.close()


# ---------------------------------------------------------------------------
# Export formatting
# ---------------------------------------------------------------------------


def _round_trip(backend: ScryfallBackend, line: str) -> str:
    """Export the card a line resolves to, and return the re-exportable text."""
    entry = ScryfallBackend.parse_line(line)
    card = backend.resolve([entry])[0].card
    assert card is not None, line
    return ScryfallBackend.export_card_text(card, entry)


def test_export_marks_foil_requests(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="m12", set="m12", collector_number="182", finishes=["nonfoil", "foil"])])
    assert _round_trip(backend, "1 Llanowar Elves (m12) 182 *F*") == "Llanowar Elves (m12) 182 *F*"


def test_export_leaves_nonfoil_untouched(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="m12", set="m12", collector_number="182")])
    assert _round_trip(backend, "1 Llanowar Elves (m12) 182") == "Llanowar Elves (m12) 182"


def test_export_converts_a_star_collector_number(tmp_path: Path) -> None:
    backend = _backend(tmp_path, [_card(id="star", set="7ed", collector_number="231★", finishes=["foil"])])
    assert _round_trip(backend, "1 Llanowar Elves 231") == "Llanowar Elves (7ed) 231 *F*"


def test_unresolved_cards_are_left_out_of_the_export(tmp_path: Path) -> None:
    """A card that does not exist has no printing, so it must not be exported."""
    backend = _backend(tmp_path, [_card(id="m12", set="m12", collector_number="182")])
    entries = [ScryfallBackend.parse_line(line) for line in ("1 Llanowar Elves", "1 Not A Real Card")]
    resolutions = backend.resolve(entries)
    exported = [ScryfallBackend.export_card_text(r.card, r.entry) for r in resolutions if r.card is not None]
    assert exported == ["Llanowar Elves (m12) 182"]


def test_exported_text_reimports_to_the_same_printing(tmp_path: Path) -> None:
    """Every exported line must parse back to the card it came from."""
    cards = [
        _card(id="m12", set="m12", collector_number="182", finishes=["nonfoil", "foil"]),
        _card(id="star", set="7ed", collector_number="231★", finishes=["foil"]),
        _card(id="plain", set="fdn", collector_number="227", finishes=["nonfoil"], released_at="2024-11-15"),
        _card(id="dfc", name="Fire // Ice", set="apc", collector_number="128", oracle_id="o-fire"),
    ]
    backend = _backend(tmp_path, cards)
    for line in (
        "1 Llanowar Elves",
        "1 Llanowar Elves (m12) 182",
        "1 Llanowar Elves (m12) 182 *F*",
        "1 Llanowar Elves (7ed) 231",
        "4 Fire // Ice",
    ):
        original = backend.resolve([ScryfallBackend.parse_line(line)])[0].card
        assert original is not None, line
        exported = _round_trip(backend, line)
        reimported = backend.resolve([ScryfallBackend.parse_line(f"1 {exported}")])[0].card
        assert reimported is not None, f"{line} -> {exported!r} did not re-import"
        assert reimported.print_id == original.print_id, f"{line} -> {exported!r}"


def test_export_is_stable_when_applied_twice(tmp_path: Path) -> None:
    """Re-exporting an already-exported list must not drift."""
    backend = _backend(tmp_path, [_card(id="star", set="7ed", collector_number="231★", finishes=["foil"])])
    once = _round_trip(backend, "1 Llanowar Elves 231")
    twice = _round_trip(backend, f"1 {once}")
    assert once == twice == "Llanowar Elves (7ed) 231 *F*"
