"""Forge screenshot text normalization, binarization, and Tesseract OCR."""

from __future__ import annotations

import importlib
import re
from typing import TYPE_CHECKING

import cv2
import numpy as np
from PIL import Image

from .runtime_config import default_tessdata_dir

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from numpy.typing import NDArray

type Region = tuple[int, int, int, int]


def binarize_image(pil_image: Image.Image, *, debug: bool = True, debug_images: bool = True) -> NDArray[np.uint8]:
    gray = np.asarray(pil_image.convert("L"), dtype=np.uint8)
    threshold, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if debug:
        print(f"Darkest pixel: {np.min(gray)}, brightest pixel: {np.max(gray)}.")
        print(f"Threshold value: {threshold}.")
    if debug_images:
        cv2.imwrite("debug_binarize_image_gray.png", gray)
        cv2.imwrite("debug_binarize_image_binary.png", binary)
    return binary.astype(np.uint8, copy=False)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def find_text_in_screen(  # noqa: PLR0913
    pattern: str,
    region: Region | None = None,
    screenshot: Image.Image | None = None,
    allowlist: str | None = None,
    flags: int = re.IGNORECASE,
    *,
    tessdata_dir: Path | None = None,
    screenshot_provider: Callable[[], Image.Image] | None = None,
    debug: bool = True,
    debug_images: bool = True,
) -> re.Match[str] | None:
    if screenshot is None:
        if screenshot_provider is None:
            message = "A screenshot or screenshot provider is required for OCR."
            raise ValueError(message)
        screenshot = screenshot_provider()
    if region is not None:
        left, top, width, height = region
        screenshot = screenshot.crop((left, top, left + width, top + height))
    binary = binarize_image(screenshot, debug=debug, debug_images=debug_images)
    tesserocr = importlib.import_module("tesserocr")
    variables: dict[str, str] = {}
    if bool(allowlist):
        variables["tessedit_char_whitelist"] = str(allowlist)
    with tesserocr.PyTessBaseAPI(
        path=str(tessdata_dir or default_tessdata_dir()), psm=tesserocr.PSM.SINGLE_LINE, variables=variables
    ) as tess_api:
        tess_api.SetImage(Image.fromarray(binary))
        ocr_text = tess_api.GetUTF8Text()
    normalized_ocr = normalize_text(ocr_text)
    match = re.search(pattern, normalized_ocr, flags)
    if match:
        if debug:
            print(f"Pattern {pattern!r} found on screen.")
    elif debug:
        print(f"Pattern {pattern!r} not found on screen.")
        print(f"OCR result was:\n{normalized_ocr!r}")
    return match
