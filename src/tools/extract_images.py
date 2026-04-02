import base64
import io
from typing import Optional, Tuple
from PIL import Image

from src.core.router import FormatRouter
from src.parsers.registry import get_parser
from src.models.image import ImageRef
from src.core.security import validate_safe_path
from src.core.logging import get_logger

logger = get_logger(__name__)


def _resize_image(image_ref: ImageRef, max_dim: int) -> ImageRef:
    """Resizes an image if it exceeds max_dimension."""
    try:
        data = base64.b64decode(image_ref.base64_data)
        img = Image.open(io.BytesIO(data))
        if img.width <= 0 or img.height <= 0:
            return image_ref

        ratio = min(max_dim / img.width, max_dim / img.height)
        if ratio >= 1.0:
            return image_ref

        new_size = (int(img.width * ratio), int(img.height * ratio))
        resized = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        fmt = (image_ref.format or 'PNG').upper()
        resized.save(buf, format='JPEG' if fmt == 'JPG' else fmt)
        
        raw = buf.getvalue()
        return ImageRef(
            index=image_ref.index,
            page=image_ref.page,
            width_px=new_size[0],
            height_px=new_size[1],
            format=image_ref.format,
            size_bytes=len(raw),
            base64_data=base64.b64encode(raw).decode('ascii'),
            description_hint=image_ref.description_hint,
            confidence=image_ref.confidence
        )
    except Exception as e:
        logger.error("image_resize_failed", index=image_ref.index, error=str(e))
        return image_ref


async def extract_images(
    path: str,
    page_range: Optional[Tuple[int, int]] = None,
    max_dimension: Optional[int] = None
) -> list[ImageRef]:
    """
    Extracts images from a file with optional filtering and resizing.

    Args:
        path: Validated path to the file.
        page_range: Inclusive (start, end) page filter.
        max_dimension: Max width/height for resizing.

    Returns:
        List of ImageRef objects.
    """
    safe_path = validate_safe_path(path)
    logger.info("tool_extract_images_start", path=str(safe_path))

    fmt = FormatRouter().detect(str(safe_path))
    parser = get_parser(fmt)
    result = await parser.parse(safe_path)

    images = result.images
    if page_range:
        s, e = page_range
        images = [i for i in images if i.page and s <= i.page <= e]

    if max_dimension and max_dimension > 0:
        images = [_resize_image(img, max_dimension) for img in images]

    logger.info("tool_extract_images_complete", count=len(images))
    return images

