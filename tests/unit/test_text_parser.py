import os
import tempfile
from pathlib import Path

import pytest
import fitz

from src.parsers.text_parser import TextParser
from src.models.enums import FileFormat, ParseStatus, SectionType


@pytest.mark.asyncio
async def test_text_parser_utf8_file(tmp_path):
    p = tmp_path / 'sample.txt'
    p.write_text('Hello world\n\nSecond paragraph', encoding='utf-8')

    parser = TextParser()
    result = await parser.parse(p)

    assert result.status == ParseStatus.OK
    assert result.metadata.file_format == FileFormat.TEXT
    assert result.metadata.section_count == 2
    assert 'Hello world' in result.sections[0].content
    assert 'Second paragraph' in result.sections[1].content


@pytest.mark.asyncio
async def test_text_parser_latin1_file(tmp_path):
    content = 'Caf\xe9 au lait\n\nDeuxieme paragraphe'
    p = tmp_path / 'latin1.txt'
    p.write_bytes(content.encode('latin-1'))

    parser = TextParser()
    result = await parser.parse(p)

    assert result.status == ParseStatus.OK
    assert result.metadata.file_format == FileFormat.TEXT
    assert 'Café au lait' in result.raw_text


@pytest.mark.asyncio
async def test_text_parser_markdown_headings(tmp_path):
    p = tmp_path / 'sample.md'
    p.write_text('# Title\n\n## Subtitle\n\n- item1\n- item2', encoding='utf-8')

    parser = TextParser()
    result = await parser.parse(p)

    assert result.status == ParseStatus.OK
    assert result.metadata.file_format == FileFormat.MARKDOWN
    assert result.metadata.section_count >= 3
    assert any(s.type == SectionType.HEADING and s.content == 'Title' for s in result.sections)
    assert any(s.type == SectionType.HEADING and s.content == 'Subtitle' for s in result.sections)
    assert any(s.type == SectionType.LIST for s in result.sections)


@pytest.mark.asyncio
async def test_text_parser_empty_file(tmp_path):
    p = tmp_path / 'empty.txt'
    p.write_text('', encoding='utf-8')

    parser = TextParser()
    result = await parser.parse(p)

    assert result.status == ParseStatus.OK
    assert result.metadata.section_count == 0
    assert result.raw_text == ''


@pytest.mark.asyncio
async def test_text_parser_oversize_rejected(tmp_path):
    p = tmp_path / 'large.txt'
    # generate a file just over 1 MB
    p.write_bytes(b'a' * 1024 * 1024 * 1 + b'b')

    parser = TextParser()
    result = await parser.parse(p, options={'max_size_mb': 1, 'max_stream_file_size_mb': 5})

    assert result.status == ParseStatus.OVERSIZE
    assert result.errors and result.errors[0].code == 'oversize'


@pytest.mark.asyncio
async def test_pdf_parser_streaming_large_but_within_stream_limit():
    from src.parsers.pdf_parser import PDFParser

    # create a 2 MB PDF using multiple pages
    doc = fitz.open()
    page_index = 0
    while page_index < 10:
        page = doc.new_page()
        page.insert_text((72, 72), 'Hello world ' * 500)
        page_index += 1
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    tmp.close()
    doc.save(tmp.name)
    doc.close()

    try:
        parser = PDFParser()
        sections = []
        async for section in parser.stream_sections(Path(tmp.name), options={'max_size_mb': 1, 'max_stream_file_size_mb': 10}):
            sections.append(section)

        assert len(sections) > 0
    finally:
        os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_text_parser_broken_encoding_replacement(tmp_path):
    p = tmp_path / 'broken.txt'
    # bytes not valid UTF-8 but valid in cp1252 (smart quote) and may be mistranslated
    p.write_bytes(b'Hello \x96 World\n')

    parser = TextParser()
    result = await parser.parse(p)

    assert result.status == ParseStatus.OK
    assert 'Hello' in result.raw_text
    # we allow replacement, so should not crash and should contain replacement char or decode it
    assert '\uFFFD' in result.raw_text or '–' in result.raw_text

