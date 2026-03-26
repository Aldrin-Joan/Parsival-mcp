from src.models.parse_result import ParseResult, Section, ParseError
from src.models.metadata import DocumentMetadata


def test_parse_result_basics():
    metadata = DocumentMetadata(source_path="/tmp/f", file_format="pdf")
    section = Section(index=0, type="paragraph", content="Hello", metadata={})
    result = ParseResult(
        status="ok",
        metadata=metadata,
        sections=[section],
        images=[],
        tables=[],
        errors=[],
        raw_text="Hello",
        cache_hit=False,
        request_id="uuid",
    )
    assert result.metadata.source_path == "/tmp/f"
    assert result.sections[0].content == "Hello"
    assert result.status == "ok"
