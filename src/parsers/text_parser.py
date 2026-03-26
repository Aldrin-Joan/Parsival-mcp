from __future__ import annotations
import chardet
import time
from pathlib import Path
from typing import Literal

from markdown_it import MarkdownIt

from src.models.enums import FileFormat, ParseStatus, SectionType
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseResult, ParseError, Section
from src.parsers.base import BaseParser
from src.parsers.registry import register


def _detect_encoding(raw_bytes: bytes) -> str:
    guess = chardet.detect(raw_bytes)
    if not guess or not guess.get('encoding'):
        return 'utf-8'
    enc = guess['encoding']
    # Normalize known nonstandard names
    if enc.lower() in ('ascii',):
        return 'utf-8'
    return enc


def _parse_markdown(text: str) -> list[Section]:
    md = MarkdownIt()
    tokens = md.parse(text)

    sections: list[Section] = []
    idx = 0

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.type == 'heading_open':
            level = int(token.tag[1]) if token.tag.startswith('h') and token.tag[1:].isdigit() else 1
            next_token = tokens[i + 1] if i + 1 < len(tokens) else None
            heading_text = ''
            if next_token and next_token.type == 'inline':
                heading_text = ''.join([t.content for t in next_token.children or []]).strip()
            if heading_text:
                sections.append(Section(index=idx, type=SectionType.HEADING, content=heading_text, level=level, confidence=0.95))
                idx += 1
            i += 2
            continue

        if token.type == 'paragraph_open':
            next_token = tokens[i + 1] if i + 1 < len(tokens) else None
            paragraph_text = ''
            if next_token and next_token.type == 'inline':
                paragraph_text = ''.join([t.content for t in next_token.children or []]).strip()
            if paragraph_text:
                sections.append(Section(index=idx, type=SectionType.PARAGRAPH, content=paragraph_text, confidence=0.85))
                idx += 1
            i += 2
            continue

        if token.type in ('list_item_open',):
            # collect list item markup until list_item_close
            list_text_items = []
            j = i + 1
            while j < len(tokens) and tokens[j].type != 'list_item_close':
                tok = tokens[j]
                if tok.type == 'inline':
                    list_text_items.append(''.join([t.content for t in tok.children or []]).strip())
                j += 1
            if list_text_items:
                sections.append(Section(index=idx, type=SectionType.LIST, content='\n'.join(list_text_items), confidence=0.85))
                idx += 1
            i = j + 1
            continue

        if token.type == 'fence':
            code_text = token.content.strip()
            if code_text:
                sections.append(Section(index=idx, type=SectionType.CODE, content=code_text, confidence=0.8))
                idx += 1
            i += 1
            continue

        i += 1

    return sections


@register(FileFormat.TEXT)
@register(FileFormat.MARKDOWN)
class TextParser(BaseParser):

    async def parse(self, path: Path, options: dict | None = None) -> ParseResult:
        source = Path(path)
        if not source.exists():
            return ParseResult(
                status=ParseStatus.FAILED,
                metadata=DocumentMetadata(source_path=str(source), file_format=FileFormat.TEXT, file_size_bytes=0),
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code='not_found', message='Text file not found', recoverable=False)],
                raw_text='',
                cache_hit=False,
                request_id='',
            )

        raw_bytes = source.read_bytes()
        encoding = _detect_encoding(raw_bytes)
        text = raw_bytes.decode(encoding, errors='replace')

        is_markdown = source.suffix.lower() in ('.md', '.markdown')

        sections: list[Section] = []

        if is_markdown:
            sections = _parse_markdown(text)
        else:
            paragraphs = [p.strip() for p in __import__('re').split(r'\r?\n\r?\n+', text) if p.strip()]
            if not paragraphs and text.strip():
                paragraphs = [text.strip()]
            for idx, para in enumerate(paragraphs):
                sections.append(Section(index=idx, type=SectionType.PARAGRAPH, content=para, confidence=0.85))

        if not sections and text.strip() == '':
            sections = []

        raw_text = text

        metadata = DocumentMetadata(
            source_path=str(source),
            file_format=FileFormat.MARKDOWN if is_markdown else FileFormat.TEXT,
            file_size_bytes=source.stat().st_size,
            page_count=None,
            section_count=len(sections),
            table_count=0,
            image_count=0,
            has_toc=any(s.type == SectionType.HEADING for s in sections),
            toc=[],
            word_count=len(text.split()),
            char_count=len(text),
            reading_time_minutes=None,
            parse_duration_ms=0.0,
            parser_version='text_parser',
        )

        status = ParseStatus.OK if sections or text.strip() == '' else ParseStatus.FAILED

        return ParseResult(
            status=status,
            metadata=metadata,
            sections=sections,
            images=[],
            tables=[],
            errors=[],
            raw_text=raw_text,
            cache_hit=False,
            request_id='',
        )

    async def parse_metadata(self, path: Path) -> DocumentMetadata:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError('Text file not found')

        raw_bytes = source.read_bytes()
        encoding = _detect_encoding(raw_bytes)
        text = raw_bytes.decode(encoding, errors='replace')

        return DocumentMetadata(
            source_path=str(source),
            file_format=FileFormat.MARKDOWN if source.suffix.lower() in ('.md', '.markdown') else FileFormat.TEXT,
            file_size_bytes=source.stat().st_size,
            page_count=None,
            section_count=0,
            table_count=0,
            image_count=0,
            has_toc=False,
            toc=[],
            word_count=len(text.split()),
            char_count=len(text),
            reading_time_minutes=None,
            parse_duration_ms=0.0,
            parser_version='text_parser',
        )
