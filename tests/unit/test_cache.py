import os
import tempfile
from src.core.cache import ContentHashStore
from src.models.parse_result import ParseResult, Section
from src.models.metadata import DocumentMetadata
from src.models.enums import ParseStatus


def test_cache_get_set_invalidate():
    cache = ContentHashStore(max_bytes=1024 * 1024)

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"hello world")
        path = f.name

    try:
        key = cache.make_cache_key(path, options={"output_format": "markdown", "page_range": [1, 1], "include_images": True})
        meta = DocumentMetadata(source_path=path, file_format="text")
        result = ParseResult(status=ParseStatus.OK, metadata=meta, sections=[], images=[], tables=[], errors=[], raw_text="", cache_hit=False, request_id="1")

        import asyncio

        async def run():
            await cache.set(key, result)
            got = await cache.get(key)
            assert got is not None
            assert got.metadata.file_format == "text"
            await cache.invalidate(key)
            got_none = await cache.get(key)
            assert got_none is None

        asyncio.run(run())
    finally:
        os.unlink(path)
