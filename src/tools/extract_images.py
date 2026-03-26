from pathlib import Path
from typing import Optional, Tuple

from PIL import Image
import base64
import io

from src.core.router import FormatRouter
from src.parsers.registry import get_parser
from src.models.image import ImageRef


def _resize_image(image_ref: ImageRef, max_dimension: int) -> ImageRef:
    try:
        image_data = base64.b64decode(image_ref.base64_data)
        image = Image.open(io.BytesIO(image_data))
        if image.width <= 0 or image.height <= 0:
            return image_ref

        ratio = min(max_dimension / image.width, max_dimension / image.height)
        if ratio >= 1.0:
            return image_ref

        new_size = (int(image.width * ratio), int(image.height * ratio))
        resized = image.resize(new_size, Image.LANCZOS)

        out_stream = io.BytesIO()
        fmt = image_ref.format.upper() if image_ref.format else 'PNG'
        if fmt == 'JPG':
            fmt = 'JPEG'
        resized.save(out_stream, format=fmt)
        encoded = base64.b64encode(out_stream.getvalue()).decode('ascii')

        return ImageRef(
            index=image_ref.index,
            page=image_ref.page,
            width_px=new_size[0],
            height_px=new_size[1],
            format=image_ref.format,
            size_bytes=len(out_stream.getvalue()),
            base64_data=encoded,
            description_hint=image_ref.description_hint,
            confidence=image_ref.confidence,
            alt_text=image_ref.alt_text,
        )
    except Exception:
        return image_ref


def _in_page_range(image: ImageRef, page_range: Optional[Tuple[int, int]]) -> bool:
    if page_range is None:
        return True
    if image.page is None:
        return True
    start, end = page_range
    return start <= image.page <= end


async def extract_images(path: str, page_range: Optional[Tuple[int, int]] = None, max_dimension: Optional[int] = None) -> list[ImageRef]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f'File not found: {path}')

    fmt = FormatRouter().detect(path)
    parser = get_parser(fmt)
    result = await parser.parse(source)

    images = [img for img in result.images if _in_page_range(img, page_range)]

    if max_dimension is not None and max_dimension > 0:
        images = [_resize_image(img, max_dimension) for img in images]

    return images
