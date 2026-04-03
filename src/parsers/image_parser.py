from __future__ import annotations

import base64
import time
from pathlib import Path

from PIL import Image

from src.models.enums import FileFormat, ParseStatus, SectionType
from src.models.image import ImageRef
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseError, ParseResult, Section
from src.parsers.base import BaseParser
from src.parsers.ocr import ocr_text_from_bytes
from src.parsers.registry import register


@register(FileFormat.IMAGE)
class ImageParser(BaseParser):
    async def parse(self, path: Path, options: dict | None = None) -> ParseResult:
        src = Path(path)
        start = time.time()

        try:
            raw = src.read_bytes()
            with Image.open(src) as image:
                width, height = image.size
                fmt = (image.format or "png").lower()
        except Exception as exc:
            metadata = DocumentMetadata(
                source_path=str(src),
                file_format=FileFormat.IMAGE,
                file_size_bytes=src.stat().st_size if src.exists() else 0,
                section_count=0,
                table_count=0,
                image_count=0,
                has_toc=False,
            )
            return ParseResult(
                status=ParseStatus.FAILED,
                metadata=metadata,
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code="invalid_image", message=str(exc), recoverable=False)],
                raw_text="",
                cache_hit=False,
                request_id="",
            )

        text, ocr_error = ocr_text_from_bytes(raw)
        errors = []
        status = ParseStatus.OK
        if ocr_error:
            errors.append(ParseError(code="ocr_error", message=ocr_error, recoverable=True))
            status = ParseStatus.PARTIAL

        section_text = text.strip()
        sections = []
        if section_text:
            sections.append(
                Section(
                    index=0,
                    type=SectionType.PARAGRAPH,
                    content=section_text,
                    page=1,
                    confidence=0.75,
                    metadata={"source": "image_ocr"},
                )
            )
        else:
            status = ParseStatus.FAILED

        image_ref = ImageRef(
            index=0,
            page=1,
            width_px=width,
            height_px=height,
            format=fmt,
            size_bytes=len(raw),
            base64_data=base64.b64encode(raw).decode("ascii"),
            description_hint=f"Image OCR source: {src.name}",
            confidence=1.0,
            alt_text=None,
        )

        metadata = DocumentMetadata(
            source_path=str(src),
            file_format=FileFormat.IMAGE,
            file_size_bytes=src.stat().st_size,
            page_count=1,
            word_count=len(section_text.split()),
            char_count=len(section_text),
            reading_time_minutes=None,
            section_count=len(sections),
            table_count=0,
            image_count=1,
            has_toc=False,
            toc=[],
            parse_duration_ms=(time.time() - start) * 1000,
            parser_version="image_ocr_v1",
        )

        return ParseResult(
            status=status,
            metadata=metadata,
            sections=sections,
            images=[image_ref],
            tables=[],
            errors=errors,
            raw_text=section_text,
            cache_hit=False,
            request_id="",
        )

    async def parse_metadata(self, path: Path) -> DocumentMetadata:
        src = Path(path)
        try:
            with Image.open(src) as image:
                width, height = image.size
        except Exception:
            width, height = None, None

        return DocumentMetadata(
            source_path=str(src),
            file_format=FileFormat.IMAGE,
            file_size_bytes=src.stat().st_size if src.exists() else 0,
            page_count=1,
            section_count=0,
            table_count=0,
            image_count=1,
            has_toc=False,
            toc=[],
            parse_duration_ms=0.0,
            parser_version=f"image_metadata_{width}x{height}" if width and height else "image_metadata_unknown",
        )
