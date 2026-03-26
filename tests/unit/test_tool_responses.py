from src.models.tool_responses import ReadFileResult, StreamChunk, SearchHit
from src.models.enums import OutputFormat, ParseStatus
from src.models.metadata import DocumentMetadata


def test_read_file_result():
    meta = DocumentMetadata(source_path="/tmp/f", file_format="pdf")
    r = ReadFileResult(
        status=ParseStatus.OK,
        format=OutputFormat.MARKDOWN,
        content="# hi",
        metadata=meta,
        errors=[],
        cache_hit=False,
        request_id="uuid",
    )
    assert r.content == "# hi"


def test_stream_chunk():
    chunk = StreamChunk(chunk_index=0, total_chunks=1, section_type="paragraph", content="x", is_final=True, request_id="uuid")
    assert chunk.is_final


def test_search_hit():
    h = SearchHit(section_index=0, page=1, snippet="x", score=1.0, offset=0)
    assert h.score == 1.0
