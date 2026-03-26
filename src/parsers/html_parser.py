from __future__ import annotations
import base64
import os
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify as markdownify_html

from src.models.enums import FileFormat, ParseStatus, SectionType
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseResult, ParseError, Section
from src.models.table import TableResult, TableCell
from src.models.image import ImageRef
from src.parsers.base import BaseParser
from src.parsers.registry import register


EXTERNAL_URL_PATTERN = re.compile(r'^https?://', re.IGNORECASE)
DATA_URI_PATTERN = re.compile(r'^data:(image/[^;]+);base64,(.+)$', re.IGNORECASE)


def _extract_table(table_tag, slide_number: int, index: int) -> TableResult:
    rows = []
    cells = []
    for r, tr in enumerate(table_tag.find_all('tr')):
        cols = []
        for c, cell in enumerate(tr.find_all(['th', 'td'])):
            text = cell.get_text(separator=' ', strip=True)
            cols.append(text)
            cells.append(
                TableCell(
                    row=r,
                    col=c,
                    value=text,
                    raw_value=text,
                    colspan=int(cell.attrs.get('colspan', 1)),
                    rowspan=int(cell.attrs.get('rowspan', 1)),
                    is_header=cell.name == 'th',
                )
            )
        if cols:
            rows.append(cols)

    headers = rows[0] if rows else []
    body = rows[1:] if len(rows) > 1 else []

    return TableResult(
        index=index,
        page=slide_number,
        caption=None,
        headers=headers,
        rows=body,
        cells=cells,
        row_count=len(body),
        col_count=len(headers),
        has_merged_cells=False,
        confidence=0.85 if rows else 0.0,
        confidence_reason='html parser',
        markdown='',
        errors=[],
    )


def _extract_images(soup) -> list[ImageRef]:
    images = []
    idx = 0

    for img in soup.find_all('img'):
        src = (img.attrs.get('src') or '').strip()
        if not src:
            continue
        if EXTERNAL_URL_PATTERN.match(src):
            continue
        if m := DATA_URI_PATTERN.match(src):
            mime, b64payload = m.groups()
            try:
                bts = base64.b64decode(b64payload)
            except Exception:
                continue
            fmt = mime.split('/')[-1]
            images.append(
                ImageRef(
                    index=idx,
                    page=None,
                    width_px=None,
                    height_px=None,
                    format=fmt,
                    size_bytes=len(bts),
                    base64_data=base64.b64encode(bts).decode('ascii'),
                    description_hint=(img.attrs.get('alt') or 'inline image'),
                    confidence=1.0,
                    alt_text=img.attrs.get('alt'),
                )
            )
            idx += 1
        else:
            # local/relative images are not explicitly supported for file access in this parser
            continue

    return images


@register(FileFormat.HTML)
class HtmlParser(BaseParser):

    async def parse(self, path: Path, options: dict | None = None) -> ParseResult:
        source = Path(path)
        if not source.exists():
            return ParseResult(
                status=ParseStatus.FAILED,
                metadata=DocumentMetadata(source_path=str(source), file_format=FileFormat.HTML, file_size_bytes=0),
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code='not_found', message='HTML file not found', recoverable=False)],
                raw_text='',
                cache_hit=False,
                request_id='',
            )

        start = time.time()
        text = source.read_text(encoding='utf-8', errors='replace')

        errors = []
        try:
            soup = BeautifulSoup(text, 'lxml')
        except Exception as exc:
            soup = BeautifulSoup(text, 'html.parser')
            errors.append(ParseError(code='html_malformed', message=str(exc), recoverable=True))

        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else None

        metas = {"description": None, "author": None, "keywords": None}
        for m in soup.find_all('meta'):
            name = (m.attrs.get('name') or '').lower()
            content = m.attrs.get('content', '').strip()
            if name in metas and content:
                metas[name] = content

        tables = []
        images = []
        sections = []
        section_idx = 0
        table_idx = 0
        image_idx = 0

        body = soup.body or soup
        for tag_name in ['script', 'style']:
            for tag in body.find_all(tag_name):
                tag.decompose()

        for elem in body.find_all(['h1','h2','h3','h4','h5','h6','p','ul','ol','pre','code','table','img'], recursive=True):
            if elem.name in ('h1','h2','h3','h4','h5','h6'):
                text_val = elem.get_text(separator=' ', strip=True)
                if text_val:
                    level = int(elem.name[1]) if elem.name[1:].isdigit() else 1
                    sections.append(Section(index=section_idx, type=SectionType.HEADING, content=text_val, page=1, level=level, confidence=0.95))
                    section_idx += 1
            elif elem.name == 'p':
                text_val = elem.get_text(separator=' ', strip=True)
                if text_val:
                    sections.append(Section(index=section_idx, type=SectionType.PARAGRAPH, content=text_val, page=1, confidence=0.85))
                    section_idx += 1
            elif elem.name in ('ul', 'ol'):
                items = [li.get_text(separator=' ', strip=True) for li in elem.find_all('li')]
                if items:
                    sections.append(Section(index=section_idx, type=SectionType.LIST, content='\n'.join(items), page=1, confidence=0.85))
                    section_idx += 1
            elif elem.name in ('pre', 'code'):
                text_val = elem.get_text('\n', strip=True)
                if text_val:
                    sections.append(Section(index=section_idx, type=SectionType.CODE, content=text_val, page=1, confidence=0.8))
                    section_idx += 1
            elif elem.name == 'table':
                try:
                    t = _extract_table(elem, slide_number=1, index=table_idx)
                    tables.append(t)
                    sections.append(Section(index=section_idx, type=SectionType.TABLE, content='', table=t, page=1, confidence=t.confidence))
                    table_idx += 1
                    section_idx += 1
                except Exception as exc:
                    errors.append(ParseError(code='table_extraction_failed', message=str(exc), recoverable=True))
            elif elem.name == 'img':
                src = (elem.attrs.get('src') or '').strip()
                if not src:
                    continue
                if EXTERNAL_URL_PATTERN.match(src):
                    continue
                m = DATA_URI_PATTERN.match(src)
                if not m:
                    continue
                mime, b64payload = m.groups()
                try:
                    payload_bytes = base64.b64decode(b64payload)
                except Exception:
                    continue
                fmt = mime.split('/')[-1]
                img_ref = ImageRef(
                    index=image_idx,
                    page=1,
                    width_px=None,
                    height_px=None,
                    format=fmt,
                    size_bytes=len(payload_bytes),
                    base64_data=base64.b64encode(payload_bytes).decode('ascii'),
                    description_hint=(elem.attrs.get('alt') or 'inline image'),
                    confidence=1.0,
                    alt_text=elem.attrs.get('alt'),
                )
                images.append(img_ref)
                sections.append(Section(index=section_idx, type=SectionType.IMAGE, content='', images=[img_ref], page=1, confidence=1.0))
                image_idx += 1
                section_idx += 1

        # Ensure title is preserved even if no h1 exists
        if title and not any(s.type == SectionType.HEADING for s in sections):
            sections.insert(0, Section(index=0, type=SectionType.HEADING, content=title, page=1, level=1, confidence=0.9))
            for idx, sec in enumerate(sections):
                sec.index = idx

        markdown_text = markdownify_html(str(body), heading_style='ATX')
        # append raw body markdown as extra paragraph if no text/heading found
        if not any(s.type in (SectionType.HEADING, SectionType.PARAGRAPH, SectionType.LIST, SectionType.CODE) for s in sections):
            sections.append(Section(index=section_idx, type=SectionType.PARAGRAPH, content=markdown_text.strip(), page=1, confidence=0.8))

        metadata = DocumentMetadata(
            source_path=str(source),
            file_format=FileFormat.HTML,
            file_size_bytes=source.stat().st_size,
            title=title,
            author=metas['author'],
            subject=None,
            keywords=metas['keywords'].split(',') if metas['keywords'] else [],
            page_count=1,
            section_count=len(sections),
            table_count=len(tables),
            image_count=len(images),
            has_toc=bool(title)
            or any(s.type == SectionType.HEADING for s in sections),
            toc=[],
            word_count=len(markdown_text.split()),
            char_count=len(markdown_text),
            reading_time_minutes=None,
            parse_duration_ms=(time.time() - start) * 1000,
            parser_version='html_parser',
        )

        metadata = DocumentMetadata(
            source_path=str(source),
            file_format=FileFormat.HTML,
            file_size_bytes=source.stat().st_size,
            title=title,
            author=metas['author'],
            subject=None,
            keywords=metas['keywords'].split(',') if metas['keywords'] else [],
            page_count=1,
            section_count=len(sections),
            table_count=len(tables),
            image_count=len(images),
            has_toc=bool(title),
            toc=[],
            word_count=len(markdown_text.split()),
            char_count=len(markdown_text),
            reading_time_minutes=None,
            parse_duration_ms=(time.time() - start) * 1000,
            parser_version='html_parser',
        )

        return ParseResult(
            status=ParseStatus.OK if not errors else ParseStatus.PARTIAL,
            metadata=metadata,
            sections=sections,
            images=images,
            tables=tables,
            errors=errors,
            raw_text=markdown_text,
            cache_hit=False,
            request_id='',
        )

    async def parse_metadata(self, path: Path) -> DocumentMetadata:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError('HTML file not found')

        text = source.read_text(encoding='utf-8', errors='replace')
        soup = BeautifulSoup(text, 'lxml')

        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else None

        metas = {"description": None, "author": None, "keywords": None}
        for m in soup.find_all('meta'):
            name = (m.attrs.get('name') or '').lower()
            content = m.attrs.get('content', '').strip()
            if name in metas and content:
                metas[name] = content

        return DocumentMetadata(
            source_path=str(source),
            file_format=FileFormat.HTML,
            file_size_bytes=source.stat().st_size,
            title=title,
            author=metas['author'],
            subject=None,
            keywords=metas['keywords'].split(',') if metas['keywords'] else [],
            page_count=1,
            section_count=0,
            table_count=0,
            image_count=0,
            has_toc=bool(title),
            toc=[],
            parse_duration_ms=0.0,
            parser_version='html_parser',
        )
