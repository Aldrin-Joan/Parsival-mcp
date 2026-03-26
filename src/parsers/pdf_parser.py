from __future__ import annotations
import asyncio
import time
from pathlib import Path
from datetime import datetime
from typing import Optional
import base64

import fitz  # PyMuPDF
try:
    import pdfplumber
except ImportError:  # type: ignore
    pdfplumber = None

from src.models.enums import FileFormat, ParseStatus, SectionType
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseResult, ParseError, Section
from src.models.table import TableResult, TableCell
from src.models.image import ImageRef
from src.parsers.base import BaseParser
from src.parsers.registry import register
from src.parsers.utils import FileOversizeError, normalize_text, enforce_file_size


@register(FileFormat.PDF)
class PDFParser(BaseParser):

    async def parse(self, path: Path, options: dict | None = None) -> ParseResult:
        start = time.time()
        src = Path(path)

        # Early oversize rejection for parse path
        try:
            enforce_file_size(src, max_size_mb=(options or {}).get('max_size_mb'), max_stream_size_mb=(options or {}).get('max_stream_file_size_mb'))
        except FileOversizeError as exc:
            metadata = DocumentMetadata(
                source_path=str(src),
                file_format=FileFormat.PDF,
                file_size_bytes=src.stat().st_size if src.exists() else 0,
                section_count=0,
                table_count=0,
                image_count=0,
                has_toc=False,
            )
            return ParseResult(
                status=ParseStatus.OVERSIZE,
                metadata=metadata,
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code='oversize', message=str(exc), recoverable=False)],
                raw_text=None,
                cache_hit=False,
                request_id='',
            )

        try:
            doc = fitz.open(str(src))
            if hasattr(doc, 'is_encrypted') and doc.is_encrypted:
                metadata = DocumentMetadata(
                    source_path=str(src),
                    file_format=FileFormat.PDF,
                    file_size_bytes=src.stat().st_size if src.exists() else 0,
                    section_count=0,
                    table_count=0,
                    image_count=0,
                    has_toc=False,
                )
                doc.close()
                return ParseResult(
                    status=ParseStatus.FAILED,
                    metadata=metadata,
                    sections=[],
                    images=[],
                    tables=[],
                    errors=[ParseError(code='encrypted', message='PDF file is password-protected', recoverable=False)],
                    raw_text=None,
                    cache_hit=False,
                    request_id='',
                )
        except Exception as exc:
            metadata = DocumentMetadata(
                source_path=str(src),
                file_format=FileFormat.PDF,
                file_size_bytes=src.stat().st_size if src.exists() else 0,
                section_count=0,
                table_count=0,
                image_count=0,
                has_toc=False,
            )
            error_code = 'corrupt'
            message = str(exc)
            if 'encrypted' in message.lower() or 'password' in message.lower():
                error_code = 'encrypted'
            return ParseResult(
                status=ParseStatus.FAILED,
                metadata=metadata,
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code=error_code, message=message, recoverable=False)],
                raw_text=None,
                cache_hit=False,
                request_id='',
            )

        sections: list[Section] = []
        raw_text_chunks: list[str] = []
        images: list[ImageRef] = []
        tables: list[TableResult] = []
        parse_errors: list[ParseError] = []

        image_index = 0
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_dict = page.get_text("dict")

            sizes: list[float] = []
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        sizes.append(span.get("size", 0.0))

            if sizes:
                median_size = sorted(sizes)[len(sizes) // 2]
            else:
                median_size = 0.0

            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                block_text = "\n".join(
                    span.get("text", "")
                    for line in block.get("lines", [])
                    for span in line.get("spans", [])
                )
                block_text = normalize_text(block_text.strip())
                if not block_text:
                    continue

                span_sizes = [span.get("size", 0.0) for line in block.get("lines", []) for span in line.get("spans", [])]
                avg_size = sum(span_sizes) / len(span_sizes) if span_sizes else 0.0
                is_heading = (median_size > 0 and avg_size >= 1.3 * median_size) or block_text.isupper()
                section_type = SectionType.HEADING if is_heading else SectionType.PARAGRAPH

                idx = len(sections)
                sections.append(
                    Section(
                        index=idx,
                        type=section_type,
                        content=block_text,
                        page=page_num + 1,
                        level=1 if is_heading else None,
                        metadata={},
                    )
                )
                raw_text_chunks.append(block_text)

            # Image extraction
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    png = doc.extract_image(xref)
                    img_bytes = png.get("image")
                    if not img_bytes:
                        continue
                    fmt = png.get("ext", "png")
                    b64 = base64.b64encode(img_bytes).decode("ascii")
                    image_obj = ImageRef(
                        index=image_index,
                        page=page_num + 1,
                        width_px=png.get("width"),
                        height_px=png.get("height"),
                        format=fmt,
                        size_bytes=len(img_bytes),
                        base64_data=b64,
                        description_hint=f"Image {image_index+1} on page {page_num+1}",
                        confidence=1.0,
                        alt_text=None,
                    )
                    images.append(image_obj)
                    image_index += 1
                except Exception as exc:
                    parse_errors.append(ParseError(code="image_extract_failed", message=str(exc), page=page_num + 1, recoverable=True))

        # Table extraction via pdfplumber
        if pdfplumber is not None:
            try:
                with pdfplumber.open(str(src)) as pb_doc:
                    table_index = 0
                    for page_num, p in enumerate(pb_doc.pages):
                        raw_tables = p.extract_tables() or []
                        for raw_tab in raw_tables:
                            cleaned: list[list[str]] = []
                            max_cols = max((len(r) for r in raw_tab), default=0)
                            for r in raw_tab:
                                row = [str(c) if c is not None else "" for c in r]
                                if len(row) < max_cols:
                                    row += [""] * (max_cols - len(row))
                                elif len(row) > max_cols:
                                    row = row[:max_cols]
                                cleaned.append(row)

                            headers = cleaned[0] if cleaned else []
                            cells: list[TableCell] = []
                            for ri, row in enumerate(cleaned):
                                for ci, val in enumerate(row):
                                    cells.append(TableCell(row=ri, col=ci, value=str(val), raw_value=val, colspan=1, rowspan=1, is_header=(ri == 0)))

                            table_obj = TableResult(
                                index=table_index,
                                page=page_num + 1,
                                caption=None,
                                headers=headers,
                                rows=cleaned[1:] if len(cleaned) > 1 else [],
                                cells=cells,
                                row_count=max(0, len(cleaned) - 1),
                                col_count=max_cols,
                                has_merged_cells=False,
                                confidence=0.8 if max_cols > 0 else 0.0,
                                confidence_reason="pdfplumber detected",
                                markdown="",
                                errors=[],
                            )
                            tables.append(table_obj)
                            table_index += 1
            except Exception as exc:
                parse_errors.append(ParseError(code="table_extract_failed", message=str(exc), page=None, recoverable=True))
        else:
            # no pdfplumber installed; table extraction unavailable
            pass

        metadata = DocumentMetadata(
            source_path=str(src),
            file_format=FileFormat.PDF,
            file_size_bytes=src.stat().st_size,
            page_count=doc.page_count,
            word_count=sum(len(s.content.split()) for s in sections),
            char_count=sum(len(s.content) for s in sections),
            reading_time_minutes=None,
            section_count=len(sections),
            table_count=len(tables),
            image_count=len(images),
            has_toc=any(s.type == SectionType.HEADING for s in sections),
            toc=[],
            parse_duration_ms=(time.time() - start) * 1000,
            parser_version=fitz.__version__,
        )

        return ParseResult(
            status=ParseStatus.OK,
            metadata=metadata,
            sections=sections,
            images=images,
            tables=tables,
            errors=parse_errors,
            raw_text=normalize_text("\n".join(raw_text_chunks)),
            cache_hit=False,
            request_id="",
        )

    async def stream_sections(self, path: Path, options: dict | None = None):
        src = Path(path)
        try:
            enforce_file_size(src, max_size_mb=(options or {}).get('max_size_mb'), max_stream_size_mb=(options or {}).get('max_stream_file_size_mb'), stream_mode=True)
        except FileOversizeError as exc:
            # Too big even for streaming, yield nothing and return.
            return

        doc = fitz.open(str(src))
        page_delay = 0.0
        if options is not None:
            page_delay = float(options.get("simulate_page_delay", 0.0))

        section_index = 0
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_dict = page.get_text("dict")

            sizes: list[float] = []
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        sizes.append(span.get("size", 0.0))

            if sizes:
                median_size = sorted(sizes)[len(sizes) // 2]
            else:
                median_size = 0.0

            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                block_text = normalize_text(
                    "\n".join(
                        span.get("text", "")
                        for line in block.get("lines", [])
                        for span in line.get("spans", [])
                    ).strip()
                )
                if not block_text:
                    continue

                span_sizes = [span.get("size", 0.0) for line in block.get("lines", []) for span in line.get("spans", [])]
                avg_size = sum(span_sizes) / len(span_sizes) if span_sizes else 0.0
                is_heading = (median_size > 0 and avg_size >= 1.3 * median_size) or block_text.isupper()
                section_type = SectionType.HEADING if is_heading else SectionType.PARAGRAPH

                section = Section(
                    index=section_index,
                    type=section_type,
                    content=block_text,
                    page=page_num + 1,
                    level=1 if is_heading else None,
                    metadata={},
                )

                yield section
                section_index += 1

            if page_delay > 0:
                await asyncio.sleep(page_delay)

    def supports_streaming(self) -> bool:
        return True

    async def parse_metadata(self, path: Path) -> DocumentMetadata:
        src = Path(path)
        doc = fitz.open(str(src))
        info = doc.metadata

        created_at: Optional[str] = info.get("creationDate")
        modified_at: Optional[str] = info.get("modDate")

        page_count = doc.page_count

        return DocumentMetadata(
            source_path=str(src),
            file_format=FileFormat.PDF,
            file_size_bytes=src.stat().st_size,
            title=info.get("title") or None,
            author=info.get("author") or None,
            subject=info.get("subject") or None,
            keywords=info.get("keywords", "").split(",") if info.get("keywords") else [],
            created_at=created_at,
            modified_at=modified_at,
            producer=info.get("producer") or None,
            page_count=page_count,
            section_count=0,
            table_count=0,
            image_count=0,
            has_toc=False,
            toc=[],
            parse_duration_ms=0.0,
            parser_version=fitz.__version__,
        )
