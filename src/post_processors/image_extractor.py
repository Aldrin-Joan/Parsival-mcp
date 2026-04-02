from __future__ import annotations
from PIL import Image
from io import BytesIO
import base64

from src.models.parse_result import ParseResult, ImageRef


class ImageExtractor:
    @staticmethod
    def _normalize_image(ir: ImageRef, max_dimension: int = 2048) -> ImageRef:
        try:
            img_bytes = base64.b64decode(ir.base64_data)
            img = Image.open(BytesIO(img_bytes))
            img.verify()
        except Exception:
            return ir

        img = Image.open(BytesIO(base64.b64decode(ir.base64_data)))
        img = img.convert("RGB")
        w, h = img.size
        if w > max_dimension or h > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="PNG")
        new_bytes = buf.getvalue()
        new_b64 = base64.b64encode(new_bytes).decode("ascii")

        return ir.model_copy(
            update={
                "width_px": img.width,
                "height_px": img.height,
                "format": "png",
                "size_bytes": len(new_bytes),
                "base64_data": new_b64,
                "description_hint": ir.description_hint,
                "confidence": min(1.0, ir.confidence + 0.05),
            }
        )

    @classmethod
    def run(cls, result: ParseResult) -> ParseResult:
        images = [cls._normalize_image(img) for img in result.images]
        return result.model_copy(update={"images": images})
