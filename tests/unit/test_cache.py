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


def test_cache_redis_hit_miss(monkeypatch):
    cache = ContentHashStore(max_bytes=1024 * 1024)

    class DummyRedis:
        def __init__(self):
            self.data = {}

        async def get(self, key):
            return self.data.get(key)

        async def set(self, key, value, ex=None):
            self.data[key] = value

        async def delete(self, key):
            self.data.pop(key, None)

        async def ping(self):
            return True

    cache._redis = DummyRedis()
    cache._redis_available = True

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


def test_cache_redis_failure_fallback(monkeypatch):
    cache = ContentHashStore(max_bytes=1024 * 1024)

    class FailingRedis:
        async def get(self, key):
            raise RuntimeError("redis down")

        async def set(self, key, value, ex=None):
            raise RuntimeError("redis down")

        async def delete(self, key):
            raise RuntimeError("redis down")

    cache._redis = FailingRedis()
    cache._redis_available = True

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
