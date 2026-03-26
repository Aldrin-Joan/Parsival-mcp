# 07 — Performance Design

## 1. Caching Strategy

### 1.1 Cache Key Design

```python
import hashlib, json
from pathlib import Path

def make_cache_key(path: str, options: ParseOptions) -> str:
    # Hash file bytes — guarantees freshness even if file is replaced at same path
    file_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()

    # Options that affect output
    opts_str = json.dumps({
        "fmt":     options.output_format.value,
        "pages":   list(options.page_range) if options.page_range else None,
        "images":  options.include_images,
        "max_dim": options.max_dimension,
    }, sort_keys=True)
    opts_hash = hashlib.sha256(opts_str.encode()).hexdigest()[:16]

    return f"{file_hash}:{opts_hash}"
```

This approach has a critical implication: **reading the file bytes is required before any cache lookup.** For very large files (> 100MB), this itself takes time. Mitigation: use `mmap` for the SHA-256 computation — the OS kernel handles I/O efficiently:

```python
import mmap, hashlib
def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            h.update(mm)
    return h.hexdigest()
```

For files > `LARGE_FILE_THRESHOLD_MB` (default 100MB), use a hybrid key: `sha256(first_4MB + last_4MB + file_size)`. This is technically not a perfect content hash, but reduces hash time from ~2s to ~50ms for 1GB files, with negligible collision risk in practice.

### 1.2 In-Memory LRU Cache

```python
from cachetools import LRUCache
import sys, threading

class ContentHashStore:
    def __init__(self, max_bytes: int):
        self._lock  = threading.Lock()
        self._cache = LRUCache(maxsize=max_bytes, getsizeof=self._sizeof)

    def _sizeof(self, result: ParseResult) -> int:
        # Approximation: count serialised JSON bytes
        return len(result.model_dump_json().encode())

    async def get(self, key: str) -> ParseResult | None:
        with self._lock:
            return self._cache.get(key)

    async def set(self, key: str, value: ParseResult) -> None:
        with self._lock:
            try:
                self._cache[key] = value
            except ValueError:
                # Entry larger than max_bytes — do not cache, log warning
                pass
```

**LRU eviction policy:** When the cache is full, the least recently accessed entry is evicted. This is appropriate because document workloads typically have temporal locality — a coding agent tends to re-read the same files in a session.

### 1.3 Redis Cache

```python
import redis.asyncio as aioredis
import msgpack

class RedisContentHashStore:
    def __init__(self, url: str, ttl: int):
        self._client = aioredis.from_url(url)
        self._ttl    = ttl
        self._prefix = "mcp-fs:"

    async def get(self, key: str) -> ParseResult | None:
        raw = await self._client.get(self._prefix + key)
        if raw is None:
            return None
        data = msgpack.unpackb(raw, raw=False)
        return ParseResult.model_validate(data)

    async def set(self, key: str, value: ParseResult) -> None:
        raw = msgpack.packb(value.model_dump(), use_bin_type=True)
        await self._client.setex(self._prefix + key, self._ttl, raw)
```

**Why msgpack over JSON?** For `ParseResult` objects containing base64 images, msgpack is 30–50% smaller and 3–5× faster to serialise/deserialise than JSON.

### 1.4 Cache Warming

For known-expensive files, the cache can be pre-warmed at startup:

```python
WARM_PATHS = os.getenv("MCP_WARM_PATHS", "").split(":")

@mcp.on_startup
async def warm_cache():
    for path in WARM_PATHS:
        if path and Path(path).exists():
            asyncio.create_task(_warm(path))

async def _warm(path: str):
    try:
        await read_file_impl(path, OutputFormat.MARKDOWN)
        await read_file_impl(path, OutputFormat.JSON)
        logger.info("cache_warmed", path=path)
    except Exception as e:
        logger.warning("cache_warm_failed", path=path, error=str(e))
```

---

## 2. Lazy Loading Design

### 2.1 Metadata-First Pattern

Agents should call `get_metadata` before `read_file`. The metadata call:
- Opens the file and reads only the header / properties
- Does **not** render any pages
- Does **not** extract images
- Completes in < 100ms even for 1000-page PDFs

```
Agent:   get_metadata("/reports/annual.pdf")
Server:  → title="Annual Report 2024", pages=142, tables=23, images=15
Agent:   [decides it needs pages 1-5 only]
Agent:   read_file("/reports/annual.pdf", page_range=[1,5])
```

### 2.2 Page-Range Lazy Loading

All parsers that support page ranges (PDF, PPTX) skip rendering pages outside the requested range:

```python
# PDFParser
for page_num in range(doc.page_count):
    if options.page_range and not (options.page_range[0] <= page_num+1 <= options.page_range[1]):
        continue
    page = doc.load_page(page_num)
    # ... process
```

For XLSX: `sheet_name` parameter limits parsing to a single worksheet.

### 2.3 Image Lazy Loading

When `include_images=False`, parsers skip image extraction entirely (no `fitz.extract_image()` calls, no Pillow resizing). This is the default-off option for agents that only need text.

---

## 3. Streaming Implementation

### 3.1 When to Stream

Files exceeding `STREAM_THRESHOLD_MB` (default 10MB) automatically use the streaming code path when `stream=True` is set.

### 3.2 PDF Native Streaming

```python
# PDFParser.stream_sections()
async def stream_sections(
    self, path: Path, options: ParseOptions
) -> AsyncIterator[Section]:
    loop = asyncio.get_event_loop()
    doc  = fitz.open(str(path))

    for page_num in range(doc.page_count):
        if options.page_range and not in_range(page_num+1, options.page_range):
            continue
        # Offload page rendering to process pool (CPU-bound)
        sections = await loop.run_in_executor(
            _process_pool, _render_page, path, page_num, options
        )
        for section in sections:
            yield section
```

`_render_page` is a top-level (picklable) function that opens the document independently in the worker process. This is intentional: fitz document objects are not picklable.

### 3.3 Streaming Chunk Emitter

```python
class StreamingChunkEmitter:
    def __init__(self, section_stream: AsyncIterator[Section], request_id: str):
        self._stream     = section_stream
        self._request_id = request_id
        self._queue      = asyncio.Queue(maxsize=8)  # backpressure

    async def __aiter__(self) -> AsyncIterator[StreamChunk]:
        index = 0
        async for section in self._stream:
            content = MarkdownSerializer.render_section(section)
            chunk = StreamChunk(
                chunk_index=index,
                total_chunks=None,
                section_type=section.type,
                content=content,
                is_final=False,
                request_id=self._request_id,
            )
            await self._queue.put(chunk)
            yield await self._queue.get()
            index += 1

        # Final chunk
        yield StreamChunk(
            chunk_index=index,
            total_chunks=index + 1,
            section_type=SectionType.METADATA,
            content="",
            is_final=True,
            request_id=self._request_id,
        )
```

---

## 4. Large File Handling

### 4.1 Chunking Strategy

For files > `STREAM_THRESHOLD_MB`:

| Format | Chunk Unit | Strategy |
|--------|-----------|----------|
| PDF | 1 page | Page-by-page fitz rendering |
| DOCX | 50 paragraphs | XML node batching |
| XLSX | 1000 rows | openpyxl row batch generator |
| PPTX | 1 slide | Slide-by-slide iteration |
| CSV | 10MB chunk | Polars `scan_csv().slice()` |

### 4.2 XLSX Large File Mode

Files > 10MB use openpyxl `read_only=True`:

```python
ws = load_workbook(path, read_only=True, data_only=True).active
BATCH = 1000
rows_buffer = []
for row in ws.iter_rows(values_only=True):
    rows_buffer.append([str(c) if c is not None else "" for c in row])
    if len(rows_buffer) >= BATCH:
        yield _rows_to_table_chunk(rows_buffer, offset)
        rows_buffer = []
        offset += BATCH
if rows_buffer:
    yield _rows_to_table_chunk(rows_buffer, offset)
```

**Trade-off:** `read_only=True` disables merged cell access. An `errors[]` entry is added: `ParseError(code="merged_cells_unavailable", message="read_only mode active for large file", recoverable=True)`.

### 4.3 Memory Budget

```
Per-request memory budget:
  File buffer:      file_size (mmap, so OS-managed)
  ParseResult:      ≤ 50MB (enforced by cache max_entry_size)
  Image buffer:     image_count × (max_dimension²) × 4 bytes
                    = worst case: 50 images × 2048² × 4 = ~800MB

Mitigation for image-heavy files:
  - Default max_dimension=2048
  - Process images one at a time (don't hold all in RAM simultaneously)
  - For extract_images: stream images one by one if image_count > 20
```

---

## 5. Process Pool Design

```python
# src/core/process_pool.py
from concurrent.futures import ProcessPoolExecutor
import asyncio

_pool: ProcessPoolExecutor | None = None

def init_pool(size: int) -> None:
    global _pool
    _pool = ProcessPoolExecutor(
        max_workers=size,
        initializer=_worker_init,
    )

def _worker_init():
    """Called once per worker process. Pre-import heavy libraries."""
    import fitz        # pre-loads MuPDF
    import openpyxl    # pre-loads shared C extensions
    import polars      # pre-loads Arrow

async def run_in_pool(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_pool, fn, *args)
```

Worker initialisation pre-imports heavy libraries so the first parse request does not pay the import cost (~200–500ms for fitz).

---

## 6. Memory vs Speed Tradeoffs

| Decision | Faster | Less Memory | Chosen |
|----------|--------|-------------|--------|
| mmap for hashing | ✓ | ✓ | ✓ |
| Cache full ParseResult vs just serialised string | ✓ (no re-serialise) | ✗ | Cache ParseResult, serialise per request |
| In-process LRU vs Redis | ✓ (no network) | ✗ | In-process by default |
| msgpack vs JSON for Redis | ✓ | ✓ (smaller) | ✓ |
| PIL resize before storing | ✓ (smaller cache entries) | ✓ | ✓ |
| Stream images one-at-a-time | ✗ (sequential I/O) | ✓ | Only for image_count > 20 |
| openpyxl read_only | ✗ (no merged cells) | ✓ | Only for files > 10MB |

---

## 7. LibreOffice Concurrency

```python
_libreoffice_semaphore = asyncio.Semaphore(MAX_LIBREOFFICE_WORKERS)

async def convert_doc_to_docx(path: Path, outdir: Path) -> Path:
    async with _libreoffice_semaphore:
        proc = await asyncio.create_subprocess_exec(
            "soffice", "--headless", "--convert-to", "docx",
            "--outdir", str(outdir), str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=SUBPROCESS_TIMEOUT_SEC
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise SubprocessError(f"LibreOffice timed out after {SUBPROCESS_TIMEOUT_SEC}s")

        if proc.returncode != 0:
            raise SubprocessError(f"LibreOffice failed: {stderr.decode()}")

    return outdir / (path.stem + ".docx")
```

**Why semaphore and not queue?** LibreOffice has a shared user profile directory. Running two simultaneous conversions with the same profile causes file lock conflicts. The semaphore ensures at most `MAX_LIBREOFFICE_WORKERS` (default 2) conversions happen simultaneously. Each uses `--outdir` to write to a unique temp directory.

---

## 8. Benchmarking Plan

### 8.1 Sample Files

| File | Size | Complexity |
|------|------|-----------|
| `bench_pdf_50p.pdf` | ~2MB | 50 pages, 5 tables, 10 images |
| `bench_pdf_large.pdf` | ~50MB | 500 pages, text-heavy |
| `bench_docx_100p.docx` | ~1MB | 100 pages, nested tables |
| `bench_xlsx_10k.xlsx` | ~3MB | 10,000 rows × 20 cols |
| `bench_pptx_30s.pptx` | ~5MB | 30 slides, images per slide |
| `bench_csv_100k.csv` | ~10MB | 100,000 rows |

### 8.2 Benchmark Code

```python
# tests/benchmarks/bench_pdf.py
import pytest, asyncio

@pytest.mark.benchmark(group="pdf")
def test_pdf_50p_cold(benchmark, settings):
    """Cold parse (no cache) — 50 page PDF."""
    result = benchmark(
        asyncio.run,
        read_file_impl("fixtures/bench_pdf_50p.pdf", OutputFormat.MARKDOWN)
    )
    assert result.status == ParseStatus.OK

@pytest.mark.benchmark(group="pdf")
def test_pdf_50p_warm(benchmark, primed_cache, settings):
    """Warm parse (cache hit) — should be near-zero."""
    result = benchmark(
        asyncio.run,
        read_file_impl("fixtures/bench_pdf_50p.pdf", OutputFormat.MARKDOWN)
    )
    assert result.cache_hit is True
```

### 8.3 Performance Targets

| Operation | p50 target | p95 target | p99 target |
|-----------|-----------|-----------|-----------|
| `get_metadata` (any format) | < 30ms | < 100ms | < 200ms |
| `read_file` PDF 50p (cold) | < 800ms | < 2000ms | < 4000ms |
| `read_file` DOCX 100p (cold) | < 400ms | < 1000ms | < 2000ms |
| `read_file` XLSX 10k rows (cold) | < 200ms | < 500ms | < 1000ms |
| `read_file` any format (warm) | < 5ms | < 20ms | < 50ms |
| `extract_images` PDF 10 images | < 500ms | < 1500ms | < 3000ms |
| `search_file` (post-parse) | < 50ms | < 150ms | < 300ms |
