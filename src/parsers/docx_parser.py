from __future__ import annotations
from pathlib import Path
from typing import Optional

import docx
from docx.oxml.ns import qn

from src.models.enums import FileFormat, ParseStatus, SectionType
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseResult, ParseError, Section
from src.models.table import TableResult, TableCell
from src.models.image import ImageRef
from src.parsers.base import BaseParser
from src.parsers.registry import register


@register(FileFormat.DOCX)
class DocxParser(BaseParser):

    async def parse(self, path: Path, options: dict | None = None) -> ParseResult:
        src = Path(path)
        start = __import__('time').time()

        try:
            doc = docx.Document(str(src))
        except Exception as exc:
            metadata = DocumentMetadata(
                source_path=str(src),
                file_format=FileFormat.DOCX,
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
                errors=[ParseError(code='corrupt', message=str(exc), recoverable=False)],
                raw_text=None,
                cache_hit=False,
                request_id='',
            )

        sections: list[Section] = []
        images: list[ImageRef] = []
        tables: list[TableResult] = []
        errors: list[ParseError] = []

        section_idx = 0
        table_idx = 0
        image_idx = 0

        # Strict XML traversal for order preservation
        for child in doc.element.body:
            if child.tag == qn('w:p'):
                paragraph = docx.text.paragraph.Paragraph(child, doc)
                text = paragraph.text.strip()
                if not text:
                    continue

                style_name = paragraph.style.name if paragraph.style is not None else ''
                style_lower = style_name.lower() if style_name else ''
                is_heading = 'heading' in style_lower or 'title' in style_lower
                section_type = SectionType.HEADING if is_heading else SectionType.PARAGRAPH
                level = 1
                if is_heading and style_lower.startswith('heading'):
                    try:
                        level = int(''.join(filter(str.isdigit, style_lower)) or '1')
                    except Exception:
                        level = 1

                sections.append(
                    Section(
                        index=section_idx,
                        type=section_type,
                        content=text,
                        page=None,
                        level=level if is_heading else None,
                        metadata={'style': style_name},
                    )
                )
                section_idx += 1

            elif child.tag == qn('w:tbl'):
                table = docx.table.Table(child, doc)
                rows_data = []
                for r_id, row in enumerate(table.rows):
                    row_values = [cell.text.strip() for cell in row.cells]
                    rows_data.append(row_values)

                if not rows_data:
                    continue

                headers = rows_data[0]
                body_rows = rows_data[1:]
                cells = []
                for r_id, row in enumerate(rows_data):
                    for c_id, value in enumerate(row):
                        cells.append(TableCell(row=r_id, col=c_id, value=str(value), raw_value=value, colspan=1, rowspan=1, is_header=(r_id == 0)))

                tables.append(
                    TableResult(
                        index=table_idx,
                        page=None,
                        caption=None,
                        headers=headers,
                        rows=body_rows,
                        cells=cells,
                        row_count=len(body_rows),
                        col_count=len(headers),
                        has_merged_cells=False,
                        confidence=0.9,
                        confidence_reason='docx parser',
                        markdown='',
                        errors=[],
                    )
                )
                table_idx += 1

            elif child.tag == qn('w:pict') or child.tag == qn('w:drawing'):
                # Handle images embedded in drawing frames by scanning document images
                pass

        # Extract images from inline shapes / part images
        for rel in doc.part.rels.values():
            if 'image' in rel.reltype:
                try:
                    img_bytes = rel.target_part.blob
                    fmt = rel.target_part.content_type.split('/')[-1]
                    b64 = __import__('base64').b64encode(img_bytes).decode('ascii')
                    images.append(
                        ImageRef(
                            index=image_idx,
                            page=None,
                            width_px=None,
                            height_px=None,
                            format=fmt,
                            size_bytes=len(img_bytes),
                            base64_data=b64,
                            description_hint=f'DOCX image {image_idx + 1}',
                            confidence=1.0,
                            alt_text=None,
                        )
                    )
                    image_idx += 1
                except Exception as exc:
                    errors.append(ParseError(code='image_extract_failed', message=str(exc), recoverable=True))

        metadata = DocumentMetadata(
            source_path=str(src),
            file_format=FileFormat.DOCX,
            file_size_bytes=src.stat().st_size,
            page_count=None,
            word_count=sum(len(s.content.split()) for s in sections),
            char_count=sum(len(s.content) for s in sections),
            reading_time_minutes=None,
            section_count=len(sections),
            table_count=len(tables),
            image_count=len(images),
            has_toc=any(s.type == SectionType.HEADING for s in sections),
            toc=[],
            parse_duration_ms=(__import__('time').time() - start) * 1000,
            parser_version=docx.__version__,
        )

        return ParseResult(
            status=ParseStatus.OK,
            metadata=metadata,
            sections=sections,
            images=images,
            tables=tables,
            errors=errors,
            raw_text='\n'.join([s.content for s in sections]),
            cache_hit=False,
            request_id='',
        )

    async def parse_metadata(self, path: Path) -> DocumentMetadata:
        src = Path(path)
        doc = docx.Document(str(src))
        props = doc.core_properties

        return DocumentMetadata(
            source_path=str(src),
            file_format=FileFormat.DOCX,
            file_size_bytes=src.stat().st_size,
            title=props.title,
            author=props.author,
            subject=props.subject,
            keywords=props.keywords.split(',') if props.keywords else [],
            created_at=props.created.isoformat() if props.created else None,
            modified_at=props.modified.isoformat() if props.modified else None,
            producer=None,
            page_count=None,
            section_count=0,
            table_count=0,
            image_count=0,
            has_toc=False,
            toc=[],
            parse_duration_ms=0.0,
            parser_version=docx.__version__,
        )
