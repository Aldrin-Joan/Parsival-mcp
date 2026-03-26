import hashlib
import mmap
import json
from pathlib import Path
from threading import Lock
from cachetools import LRUCache
from src.models.parse_result import ParseResult
from src.config import settings

try:
    import redis.asyncio as redis
except ImportError:
    redis = None


class ContentHashStore:
    def __init__(self, max_bytes: int = 500 * 1024 * 1024):
        self._lock = Lock()
        self._cache = LRUCache(maxsize=max_bytes, getsizeof=self._sizeof)

        # Optional Redis backend
        self._redis = None
        self._redis_available = False

        if settings.REDIS_ENABLED and redis is not None and settings.REDIS_URL:
            try:
                self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
                # on Pi and some fake env, ping can fail
                async def _check_redis():
                    await self._redis.ping()

                import asyncio
                asyncio.get_event_loop().run_until_complete(_check_redis())
                self._redis_available = True
            except Exception:
                self._redis = None
                self._redis_available = False

    def _sizeof(self, value: ParseResult) -> int:
        return len(value.model_dump_json().encode("utf-8"))

    def _hash_file(self, path: Path) -> str:
        size = path.stat().st_size
        threshold = settings.HYBRID_HASH_THRESHOLD_MB * 1024 * 1024
        if size <= threshold:
            h = hashlib.sha256()
            with path.open("rb") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    h.update(mm)
            return h.hexdigest()

        # Hybrid for large files
        h = hashlib.sha256()
        with path.open("rb") as f:
            h.update(f.read(4 * 1024 * 1024))
            f.seek(max(size - 4 * 1024 * 1024, 0))
            h.update(f.read(4 * 1024 * 1024))
        h.update(str(size).encode("utf-8"))
        return h.hexdigest()

    def make_cache_key(self, path: str, options: dict | None = None) -> str:
        file_path = Path(path)
        file_hash = self._hash_file(file_path)
        options = options or {}
        opts = {
            "fmt": options.get("output_format"),
            "page_range": options.get("page_range"),
            "include_images": options.get("include_images"),
            "max_dimension": options.get("max_dimension"),
        }
        opts_bytes = str(sorted(opts.items())).encode("utf-8")
        opts_hash = hashlib.sha256(opts_bytes).hexdigest()[:16]
        return f"{file_hash}:{opts_hash}"

    async def _get_in_memory(self, key: str) -> ParseResult | None:
        with self._lock:
            return self._cache.get(key)

    async def _set_in_memory(self, key: str, value: ParseResult) -> None:
        with self._lock:
            try:
                self._cache[key] = value
            except ValueError:
                pass

    async def _invalidate_in_memory(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    async def get(self, key: str) -> ParseResult | None:
        if self._redis_available and self._redis:
            try:
                raw = await self._redis.get(key)
                if raw is not None:
                    parsed = ParseResult.model_validate_json(raw)
                    return parsed
            except Exception:
                self._redis_available = False

        result = await self._get_in_memory(key)
        return result

    async def set(self, key: str, value: ParseResult) -> None:
        if self._redis_available and self._redis:
            try:
                payload = value.model_dump_json()
                await self._redis.set(key, payload, ex=settings.REDIS_TTL)
            except Exception:
                self._redis_available = False

        await self._set_in_memory(key, value)

    async def invalidate(self, key: str) -> None:
        if self._redis_available and self._redis:
            try:
                await self._redis.delete(key)
            except Exception:
                self._redis_available = False

        await self._invalidate_in_memory(key)
