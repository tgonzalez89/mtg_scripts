from __future__ import annotations

import numpy as np
from PIL import Image

from mtg_scripts.forge_auto_battler.ocr import binarize_image, normalize_text


def test_ocr_text_normalization_and_binary_image_helpers() -> None:
    assert normalize_text("  Forge\n  Match  ") == "Forge Match"
    binary = binarize_image(Image.new("L", (8, 8), 255), debug=False, debug_images=False)
    assert binary.shape == (8, 8)
    assert set(np.unique(binary)) <= {0, 255}
