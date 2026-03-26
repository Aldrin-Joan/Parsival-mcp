# 02 — Technology Stack

## 1. Runtime & Language

### Python 3.11+

**Justification:**  
- `asyncio` is mature and first-class — FastMCP is built on it.  
- `ProcessPoolExecutor` for CPU-bound parsing is straightforward.  
- All tier-1 parsing libraries (pymupdf, python-docx, openpyxl, python-pptx) are Python-native.  
- Type hints + Pydantic v2 give strict data contracts at runtime, not just statically.

**Minimum version: 3.11**  
Reason: `asyncio.TaskGroup`, `tomllib` (stdlib), and `ExceptionGroup` are needed. 3.12 preferred for faster asyncio.

**Rejected alternatives:**
- Node.js: No mature equivalent of pymupdf/pdfplumber. `pdf-parse` is inferior.
- Go: No ecosystem parity for DOCX/PPTX parsing without C FFI.
- Rust: Too much FFI glue; development velocity cost not justified at this stage.

---

## 2. MCP Framework

### FastMCP 2.x

**Justification:**  
- Native async; tools are plain `async def` with type annotations auto-converted to JSON Schema.  
- Built-in support for stdio, SSE, and WebSocket transports.  
- Streaming tool responses via `AsyncGenerator`.  
- Active development aligned with MCP specification evolution.

**Version:** `fastmcp>=2.0.0`

**Rejected alternatives:**
- Raw MCP SDK (`mcp`): Lower level; more boilerplate; no auto-schema generation.
- HTTP REST wrapper: Adds transport overhead; breaks MCP-native streaming.

---

## 3. Data Validation

### Pydantic v2

**Justification:**  
- `model_dump_json()` is 5–10× faster than v1 thanks to Rust core.  
- Strict mode catches type coercions that silently corrupt LLM-bound data.  
- `BaseSettings` handles environment variable parsing with type safety.  
- JSON Schema generation from models feeds directly into FastMCP tool definitions.

**Version:** `pydantic>=2.5.0`

---

## 4. PDF Parsing

### Primary: PyMuPDF (fitz) 1.24+

**Justification:**  
- C-backed (MuPDF); 10–50× faster than pypdf/pdfminer for text extraction.  
- Direct access to page layout coordinates — essential for table detection by bounding box.  
- Native image extraction: `page.get_images(full=True)` returns xref handles; `doc.extract_image(xref)` returns raw bytes.  
- Handles encrypted PDFs (user password support).  
- Accurate reading-order reconstruction with `page.get_text("blocks")`.

**Version:** `pymupdf>=1.24.0`

**Secondary: pdfplumber 0.11+**  
Used exclusively for table extraction. Its line-intersection algorithm detects borderless tables that pymupdf misses.  
`pdfplumber>=0.11.0`

**Rejected alternatives:**
- `pypdf`: Pure Python, slow, limited image extraction.
- `pdfminer.six`: Slow, no image extraction, complex API.
- `camelot-py`: Excellent table extraction but requires Ghostscript (heavy OS dependency); use pdfplumber instead.

---

## 5. Word Document Parsing

### DOCX: python-docx 1.1+

**Justification:**  
- Pure Python; no subprocess needed.  
- Full paragraph, run, style, and table access.  
- Image access via `doc.inline_shapes` and relationship parts.  
- Tracked changes accessible via raw XML (`docx.oxml`).

**Version:** `python-docx>=1.1.0`

### DOC (legacy binary format): LibreOffice 7.6+

**Justification:**  
No pure-Python solution reliably handles the binary OLE2 compound format (`.doc`). LibreOffice `soffice --headless --convert-to docx` produces a clean DOCX which is then parsed by `python-docx`.

**Version:** LibreOffice 7.6 LTS (system package: `libreoffice-headless`)

**Management:** LibreOffice is spawned once at server startup with `--norestore --headless` and kept alive as a long-running process (UNO bridge). Cold start: ~2s. Warm conversion: ~150–300ms.

**Rejected alternatives:**
- `textract`: Wraps CLI tools; unreliable, unmaintained.
- `antiword`: Deprecated; no table support.
- `docx2txt`: Text-only, no structure.

---

## 6. Spreadsheet Parsing

### XLSX: openpyxl 3.1+

**Justification:**  
- Full worksheet, merged cell, named range, and chart access.  
- Streaming `read_only=True` mode for large files (does not load full workbook into RAM).  
- Formula value caching support (reads cached values without recalculation).

**Version:** `openpyxl>=3.1.0`

### Large CSV / XLSX performance: Polars 0.20+

**Justification:**  
- Arrow-native columnar storage; CSV ingestion is 5–20× faster than pandas.  
- `scan_csv()` is lazy — no memory allocation until `.collect()`.  
- Schema inference is far more accurate than pandas defaults.  
- `polars.read_excel()` uses a Rust XLSX reader that handles files pandas/openpyxl struggle with.

**Version:** `polars>=0.20.0`

**When to use which:**  
- Structure-aware tasks (merged cells, named ranges, per-sheet parsing): openpyxl  
- Raw data extraction for large files or pure CSV: Polars

**Rejected alternatives:**
- `pandas`: Slower than Polars for ingestion; large memory footprint; no lazy evaluation.
- `xlrd`: Supports only `.xls` (legacy); deprecated for `.xlsx`.

---

## 7. Presentation Parsing

### python-pptx 0.6.23+

**Justification:**  
- Full shape, text frame, table, and image access.  
- Slide layout inheritance tree accessible.  
- Notes slide access (`slide.notes_slide.notes_text_frame`).  
- Z-order preserved via `slide.shapes` iteration order.

**Version:** `python-pptx>=0.6.23`

---

## 8. HTML Parsing

### BeautifulSoup4 + lxml

**Justification:**  
- lxml backend is C-backed; parsing is fast even for large HTML files.  
- `bs4` provides a high-level traversal API.  
- `html5lib` available as fallback for malformed HTML.

**Version:** `beautifulsoup4>=4.12.0`, `lxml>=5.0.0`

### HTML-to-Markdown: markdownify 0.12+

**Justification:**  
- Handles nested HTML tables, lists, code blocks, and hyperlinks correctly.  
- Configurable heading style (ATX), bullet character, and strip list.

**Version:** `markdownify>=0.12.0`

---

## 9. Format Detection

### python-magic 0.4.27+

**Justification:**  
- Wraps `libmagic` (the same library used by the `file` Unix command).  
- Magic byte detection is format-independent and not fooled by wrong file extensions.  
- MIME type output is standardised.

**System dependency:** `libmagic-dev` (apt) / `libmagic` (brew)  
**Version:** `python-magic>=0.4.27`

---

## 10. Caching

### In-process: cachetools 5.3+

**Justification:**  
- `LRUCache` with byte-aware size tracking via `__sizeof__`.  
- Thread-safe with `cachedmethod` decorator.  
- Zero dependencies.

**Version:** `cachetools>=5.3.0`

### Distributed: Redis 7.2 + redis-py 5.0+

**Justification:**  
- Enables shared cache across multiple FastMCP worker processes.  
- TTL support for automatic expiry.  
- `SETEX` is atomic — no race conditions on simultaneous cache writes.

**Version:** `redis>=5.0.0` (client library)

---

## 11. Async & Concurrency

### anyio 4.x (via FastMCP dependency)

**Justification:**  
- Backend-agnostic async primitives.  
- `run_sync_in_worker_thread` for wrapping blocking parser calls without blocking the event loop.  
- `CapacityLimiter` for LibreOffice worker throttling.

### concurrent.futures.ProcessPoolExecutor (stdlib)

**Justification:**  
- CPU-bound parsing (PDF, large XLSX) must run in a separate process to bypass the GIL.  
- `asyncio.get_event_loop().run_in_executor(pool, fn, *args)` integrates cleanly.

---

## 12. Image Processing

### Pillow 10.3+

**Justification:**  
- Resize images exceeding `IMAGE_MAX_DIMENSION` before base64 encoding.  
- Convert to uniform format (PNG for lossless, JPEG for photographs).  
- EXIF stripping to reduce payload size.

**Version:** `Pillow>=10.3.0`

---

## 13. Configuration

### pydantic-settings 2.x

**Version:** `pydantic-settings>=2.1.0`

---

## 14. Observability

### structlog 24+

**Justification:**  
- Structured JSON logging — parseable by Datadog, Loki, etc.  
- Async-native; does not block the event loop.  
- Context variables propagate through `asyncio` tasks.

**Version:** `structlog>=24.0.0`

### Sentry SDK (optional)

For production error tracking.  
**Version:** `sentry-sdk>=1.40.0`

---

## 15. Testing

### pytest-asyncio 0.23+

For async test functions.

### pytest-benchmark 4.0+

For parser performance regression tests.

### httpx 0.27+

For MCP HTTP/SSE transport integration tests.

---

## 16. OS-Level Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `libmagic-dev` | Format detection | `apt install libmagic-dev` |
| `libreoffice-headless` | DOC → DOCX conversion | `apt install libreoffice-headless` |
| `libpoppler-cpp-dev` | (optional) pdftotext fallback | `apt install poppler-utils` |
| `fonts-liberation` | LibreOffice font rendering | `apt install fonts-liberation` |

---

## 17. Full Requirements Summary

```
# requirements.txt  (pinned versions for reproducibility)

# Core
fastmcp>=2.0.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
anyio>=4.3.0

# Parsing
pymupdf>=1.24.0
pdfplumber>=0.11.0
python-docx>=1.1.0
python-pptx>=0.6.23
openpyxl>=3.1.0
polars>=0.20.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
markdownify>=0.12.0
python-magic>=0.4.27

# Images
Pillow>=10.3.0

# Cache
cachetools>=5.3.0
redis>=5.0.0

# Observability
structlog>=24.0.0
sentry-sdk>=1.40.0  # optional

# Dev / Test
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-benchmark>=4.0.0
httpx>=0.27.0
ruff>=0.4.0
mypy>=1.9.0
```

---

## 18. Performance Tradeoffs Summary

| Choice | Speed Gain | Cost |
|--------|-----------|------|
| pymupdf over pypdf | 10–50× for PDF | GPL licence (AGPL for pymupdf) — check compatibility |
| Polars over pandas | 5–20× for CSV/XLSX | Additional dependency; API difference |
| In-process LRU | Zero network overhead | RAM bound; lost on process restart |
| ProcessPoolExecutor | Bypasses GIL for parsing | Process spawn overhead (~50ms first call) |
| pdfplumber for tables | Better table accuracy | Slower than pymupdf-only; run only on pages with tables |
| LibreOffice hot-start | 150ms vs 2s cold | Adds ~80MB RSS baseline memory |
