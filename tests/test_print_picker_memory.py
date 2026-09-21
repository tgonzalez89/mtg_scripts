from __future__ import annotations

import ctypes
import gc
import os
import time
import weakref
from ctypes import wintypes
from typing import TYPE_CHECKING, cast

import pytest

from mtg_scripts.print_picker.print_picker import App
from mtg_scripts.print_picker.riftcodex_backend import RiftCodexBackend as RiftBoundBackend
from mtg_scripts.print_picker.view_model import CardSlot

if TYPE_CHECKING:
    from pathlib import Path

    from mtg_scripts.print_picker.card_backend import CardBackend
    from mtg_scripts.print_picker.scryfall_backend import ScryfallBackend

MAGIC_DECK = """1 Abandoned Air Temple
1 Ambrosia Whiteheart
1 Avacyn's Pilgrim
1 Avenger of Zendikar
1 Beast Whisperer
1 Beast Within
1 Birds of Paradise
1 Bridgeworks Battle
1 Brokers Hideout
1 Cabaretti Courtyard
1 Canopy Vista
1 Cleansing Nova
1 Clifftop Lookout
1 Command Tower
1 Dancing from Dark to Dawn
1 Darksteel Mutation
1 Disciple of Freyalise
1 Elvish Mystic
1 Elvish Visionary
1 Emeria Shepherd
1 Emeria's Call
1 Ezuri's Predation
1 Felidar Retreat
1 Finale of Glory
1 Flare of Fortitude
13 Forest
1 Fyndhorn Elves
1 Gallant Citizen
1 Gavony Township
1 Generous Gift
1 God-Eternal Oketra
1 Greensleeves, Maro-Sorcerer
1 Guardian Project
1 Harmonize
1 Haywire Mite
1 Helpful Hunter
1 Lifecrafter's Bestiary
1 Llanowar Elves
1 Loran of the Third Path
1 Maja, Bretagard Protector
1 Mirari's Wake
1 Mirror Entity
1 Moonshaker Cavalry
1 Multani, Yavimaya's Avatar
1 Murasa Rootgrazer
1 Path to Exile
11 Plains
1 Rampaging Baloths
1 Razorgrass Ambush
1 Rescuer Chwinga
1 Rumor Gatherer
1 Sakura-Tribe Elder
1 Sapling Nursery
1 Scattered Groves
1 Scute Swarm
1 Seer's Sundial
1 Selesnya Sanctuary
1 Selfless Spirit
1 Shalai, Voice of Plenty
1 Springbloom Druid
1 Springheart Nantuko
1 Strength of the Harvest
1 Stroke of Midnight
1 Studious First-Year
1 Summon: Fenrir
1 Sutina, Speaker of the Tajuru
1 Swords to Plowshares
1 Thraben Charm
1 Tireless Provisioner
1 Tireless Tracker
1 Turntimber Symbiosis
1 Unbreakable Formation
1 War Room
1 White Sun's Twilight
1 Witch Enchanter
1 Wood Elves
1 Woodland Acolyte
1 Karametra, God of Harvests"""

RIFTBOUND_DECK = """1 Annie - Dark Child - Starter (OGS-017)
3 Traveling Merchant (OGN-185)
2 Tibbers (OGS-018)
2 Flash (OGS-011)
2 Annie - Stubborn (OGS-010)
3 Incinerate (OGS-003)
3 Firestorm (OGS-002)
2 Annie - Fiery (OGS-001)
1 Void Gate (OGN-296)
3 Maddened Marauder (OGN-191)
3 Disintegrate (OGN-005)
3 Sneaky Deckhand (OGN-176)
3 Sai Scout (OGN-174)
3 Mystic Poro (OGN-171)
3 Morbid Return (OGN-170)
3 Gust (OGN-169)
6 Chaos Rune (OGN-166)
2 Pouty Poro (OGN-013)
6 Fury Rune (OGN-007)"""
MEMORY_TEST_TIMEOUT = 600.0


def _process_memory() -> int:
    if os.name != "nt":
        return 0

    class MemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(MemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    process_handle = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(process_handle, ctypes.byref(counters), counters.cb):
        return 0
    return counters.WorkingSetSize


def _snapshot(label: str) -> dict[str, int | str | float]:
    gc.collect()
    snapshot = {
        "label": label,
        "rss_mb": round(_process_memory() / 1024**2, 1),
        "tracked_objects": len(gc.get_objects()),
    }
    print(snapshot)
    return snapshot


def _wait_for_cards(app: App, expected_count: int, timeout: float = MEMORY_TEST_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.update()
        if len(app.card_grid.cards) == expected_count and all(not slot.image_loading for slot in app.slots):
            return
        time.sleep(0.01)
    pytest.fail(f"Timed out waiting for {expected_count} cards; got {len(app.card_grid.cards)}")


def _import_text(app: App, backend: CardBackend, text: str) -> None:
    app.backend = backend
    app.card_grid.set_backend(backend)
    app.slots = [CardSlot(entry=backend.parse_line(line)) for line in text.splitlines() if line.strip()]
    app.card_grid.clear()
    app.card_grid.load_slots(app.slots, app._resolve_slots, app._load_slot_images)
    expected_count = sum(slot.quantity for slot in app.slots)
    _wait_for_cards(app, expected_count)


def _has_single_printing(backend: ScryfallBackend, slot: CardSlot) -> bool:
    card = slot.display_print
    assert card is not None
    return len(backend.printings_of(card)) == 1


def _open_and_close_chooser(app: App, slot: CardSlot) -> dict[str, int | float]:
    name = slot.name
    app._open_chooser(slot)
    chooser = app.printing_chooser
    assert chooser is not None
    deadline = time.monotonic() + MEMORY_TEST_TIMEOUT
    while time.monotonic() < deadline:
        app.update()
        if len(chooser.card_grid.cards) > 0 and all(not card.slot.image_loading for card in chooser.card_grid.cards):
            break
        time.sleep(0.01)
    else:
        pytest.fail(f"Timed out loading chooser for {name}")
    before_close = _snapshot(f"chooser_open:{name}")
    chooser_ref = weakref.ref(chooser)
    app._close_printing_chooser()
    app.update()
    # Drop this frame's own reference, otherwise the chooser is trivially
    # reachable and the leak check below can never fail.
    del chooser
    gc.collect()
    after_close = _snapshot(f"chooser_closed:{name}")
    assert chooser_ref() is None
    assert app.printing_chooser is None
    return {
        "rss_before": cast("float", before_close["rss_mb"]),
        "rss_after": cast("float", after_close["rss_mb"]),
        "objects_before": cast("int", before_close["tracked_objects"]),
        "objects_after": cast("int", after_close["tracked_objects"]),
    }


@pytest.mark.skipif(os.getenv("RUN_PRINT_PICKER_MEMORY_TESTS") != "1", reason="opt-in integration memory test")
def test_print_picker_two_deck_memory_lifecycle(tmp_path: Path) -> None:
    app = App()
    app.withdraw()
    try:
        _snapshot("app_open")
        _import_text(app, app.backend, MAGIC_DECK)
        _snapshot("magic_import")
        scryfall_backend = cast("ScryfallBackend", app.backend)
        assert scryfall_backend._store is not None

        single_slot = next(slot for slot in app.slots if _has_single_printing(scryfall_backend, slot))
        # Released here so it cannot keep the backend alive past the swap below.
        del scryfall_backend
        birds_slot = next(slot for slot in app.slots if slot.name == "Birds of Paradise")
        forest_slot = next(slot for slot in app.slots if slot.name == "Forest")
        _open_and_close_chooser(app, single_slot)
        _open_and_close_chooser(app, birds_slot)
        forest = _open_and_close_chooser(app, forest_slot)
        assert forest["objects_after"] <= forest["objects_before"] + 10_000

        _import_text(app, app.backend, "1 Sol Ring")
        _snapshot("sol_ring_import")
        assert cast("ScryfallBackend", app.backend)._store is not None

        old_backend = app.backend
        old_backend.close()
        old_backend_ref = weakref.ref(old_backend)
        app.backend = RiftBoundBackend(cache_dir=tmp_path)
        app.card_grid.set_backend(app.backend)
        del old_backend
        _import_text(app, app.backend, RIFTBOUND_DECK)
        _snapshot("riftbound_import_same_app")
        gc.collect()
        assert old_backend_ref() is None
        assert not app.backend.supports_progress

        app.destroy()
        app = None
        gc.collect()
        _snapshot("app_closed")
        new_app = App()
        new_app.withdraw()
        try:
            new_backend = RiftBoundBackend(cache_dir=tmp_path)
            _import_text(new_app, new_backend, RIFTBOUND_DECK)
            _snapshot("new_app_riftbound_import")
        finally:
            new_app.destroy()
    finally:
        if app is not None and app.winfo_exists():
            app.destroy()
