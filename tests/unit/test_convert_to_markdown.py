import pytest

from src.tools.convert_to_markdown import convert_to_markdown
from src.serialisers.markdown import MarkdownSerializer
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseResult, Section
from src.models.enums import ParseStatus, SectionType


@pytest.mark.asyncio
async def test_convert_to_markdown_matches_serializer(tmp_path):
    sample = tmp_path / 'demo.txt'
    sample.write_text('Hello\n\nWorld', encoding='utf-8')

    md = await convert_to_markdown(str(sample))

    # result from converter should be same as MarkdownSerializer on manual ParseResult
    metadata = DocumentMetadata(
        source_path=str(sample),
        file_format='text',
        file_size_bytes=sample.stat().st_size,
        section_count=2,
        table_count=0,
        image_count=0,
        has_toc=False,
        toc=[],
        word_count=2,
        char_count=len('Hello\n\nWorld'),
        parse_duration_ms=0,
        parser_version='test',
    )

    result = ParseResult(
        status=ParseStatus.OK,
        metadata=metadata,
        sections=[
            Section(index=0, type=SectionType.PARAGRAPH, content='Hello'),
            Section(index=1, type=SectionType.PARAGRAPH, content='World'),
        ],
        images=[],
        tables=[],
        errors=[],
        raw_text='Hello\n\nWorld',
        cache_hit=False,
        request_id='',
    )

    expected = MarkdownSerializer.serialize(result)

    assert md == expected
