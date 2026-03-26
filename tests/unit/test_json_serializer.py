import json

import pytest

from src.models.enums import ParseStatus, SectionType
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseResult, Section, ParseError
from src.serialisers.json_serialiser import JSONSerializer


@pytest.mark.asyncio
async def test_json_serializer_full_dump():
    metadata = DocumentMetadata(
        source_path='fake.txt',
        file_format='text',
        file_size_bytes=42,
        section_count=1,
        table_count=0,
        image_count=0,
        has_toc=False,
        toc=[],
        word_count=3,
        char_count=14,
        parse_duration_ms=1.2,
        parser_version='test',
    )

    section = Section(index=0, type=SectionType.PARAGRAPH, content='Hello world')
    result = ParseResult(
        status=ParseStatus.OK,
        metadata=metadata,
        sections=[section],
        images=[],
        tables=[],
        errors=[],
        raw_text='Hello world',
        cache_hit=False,
        request_id='abc',
    )

    json_text = JSONSerializer.serialize(result)
    parsed = json.loads(json_text)

    assert parsed['status'] == 'ok'
    assert parsed['metadata']['source_path'] == 'fake.txt'
    assert parsed['sections'][0]['content'] == 'Hello world'


@pytest.mark.asyncio
async def test_json_serializer_stream():
    metadata = DocumentMetadata(
        source_path='fake.txt',
        file_format='text',
        file_size_bytes=34,
        section_count=2,
        table_count=0,
        image_count=0,
        has_toc=False,
        toc=[],
        word_count=4,
        char_count=20,
        parse_duration_ms=0.5,
        parser_version='test',
    )

    sections = [
        Section(index=0, type=SectionType.HEADING, content='Title'),
        Section(index=1, type=SectionType.PARAGRAPH, content='Body text')
    ]

    result = ParseResult(
        status=ParseStatus.OK,
        metadata=metadata,
        sections=sections,
        images=[],
        tables=[],
        errors=[ParseError(code='none', message='')],
        raw_text='Title\nBody text',
        cache_hit=False,
        request_id='xyz',
    )

    chunks = list(JSONSerializer.stream(result))
    assert chunks[0].strip() == '{'
    assert '"metadata"' in chunks[1]
    assert '"sections"' in chunks[2]
    assert any('"Title"' in c for c in chunks), 'Title should appear in streamed chunks'

    combined = ''.join(chunks)
    parsed = json.loads(combined)
    assert parsed['metadata']['source_path'] == 'fake.txt'
    assert parsed['sections'][0]['content'] == 'Title'
    assert parsed['status'] == 'ok'
