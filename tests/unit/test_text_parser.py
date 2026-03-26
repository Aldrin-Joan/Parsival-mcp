import pytest

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
