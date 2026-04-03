from __future__ import annotations

import io
from typing import Tuple

from PIL import Image


def ocr_text_from_pil(image: Image.Image) -> Tuple[str, str | None]:
    """Extract text from a PIL image via Tesseract when available."""
    try:
        import pytesseract  # type: ignore
    except Exception:
        return "", "pytesseract_unavailable"

    try:
        text = pytesseract.image_to_string(image) or ""
        cleaned = "\n".join(line.rstrip() for line in text.splitlines()).strip()
        if not cleaned:
            return "", "ocr_no_text_detected"
        return cleaned, None
    except Exception as exc:
        return "", f"ocr_failed: {exc}"


def ocr_text_from_bytes(image_bytes: bytes) -> Tuple[str, str | None]:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return ocr_text_from_pil(image)
    except Exception as exc:
        return "", f"image_decode_failed: {exc}"
