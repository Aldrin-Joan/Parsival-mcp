import asyncio
import tempfile
import pytest
from src.parsers.streaming_chunk_emitter import StreamingChunkEmitter
from src.models.parse_result import Section
from src.models.metadata import DocumentMetadata
from src.models.enums import SectionType


async def _generate_sections(total: int):
    for i in range(total):
        yield Section(
            index=i,
            type=SectionType.PARAGRAPH,
            content=f"section-{i}",
            page=(i // 10) + 1,
            level=None,
            metadata={},
        )


@pytest.mark.asyncio
async def test_streaming_chunk_emitter_backpressure_and_order():
    total_sections = 30
    metadata = DocumentMetadata(
        source_path="/tmp/test.pdf",
        file_format="pdf",
        file_size_bytes=123,
        page_count=3,
        section_count=0,
        table_count=0,
        image_count=0,
        has_toc=False,
    )

    emitter = StreamingChunkEmitter(_generate_sections(total_sections), metadata=metadata, request_id="test123", maxsize=8)
    seen_contents = []
    seen_page_order = []

    async for chunk in emitter:
        # slow consumer
        await asyncio.sleep(0.02)

        if not chunk.is_final:
            seen_contents.append(chunk.content)
            seen_page_order.append(int(chunk.content.split("-")[1]))
        else:
            # final chunk contains metadata and summary
            assert "metadata" in chunk.content
            assert "summary" in chunk.content

    assert len(seen_contents) == total_sections
    assert seen_page_order == list(range(total_sections))
    assert emitter.max_queue_size_observed <= 8
    assert emitter.queue.maxsize == 8
