# 04 — Implementation Plan

## 1. Guiding Principles

- **MVP in ≤ 2 weeks** for a single developer. Core parsers (PDF, DOCX, XLSX, CSV) with Markdown output and in-memory cache.
- **V1 in ≤ 5 weeks** adds all formats, streaming, image extraction, JSON output.
- **V2 in ≤ 9 weeks** adds Redis cache, OCR plugin, search, benchmarks, Docker packaging.
- Each phase produces a runnable, testable artefact. No "big bang" integrations.
- Build infrastructure first (data contracts, registry, base classes) before parsers.

---

## 2. Phase 0 — Foundations (Days 1–3)

**Goal:** Project skeleton that compiles, tests pass, no parsing yet.

### Steps:

1. **Initialise project structure** (see `06_Project_Structure.md`)  
   - Create all directories and `__init__.py` files  
   - Set up `pyproject.toml` with dependencies  
   - Configure `ruff`, `mypy`, `pytest` in `pyproject.toml`  

2. **Define all Pydantic models** (`src/models/`)  
   - `FileFormat`, `ParseStatus`, `SectionType` enums  
   - `DocumentMetadata`, `Section`, `ImageRef`, `TableResult`, `ParseResult`  
   - `ReadFileResult`, `StreamChunk`, `SearchHit`  
   - Write unit tests: model instantiation, JSON round-trip, schema generation  

3. **Implement `BaseParser` abstract class** (`src/parsers/base.py`)  
   - `parse()`, `parse_metadata()`, `stream_sections()` interfaces  
   - Default `stream_sections()` that buffers full parse then yields  
   - `supports_streaming()` flag  

4. **Implement `ParserRegistry`** (`src/parsers/registry.py`)  
   - `@register(FileFormat.X)` decorator  
   - `get_parser(fmt)` lookup  
   - `list_supported_formats()` tool  

5. **Implement `FormatRouter`** (`src/core/router.py`)  
   - Three-pass detection: magic bytes → extension → content sniff  
   - Unit tests with real files of each format  

6. **Implement `Settings`** (`src/config.py`)  
   - All env vars with defaults  
   - Validate on startup (e.g. LibreOffice path exists if `DOC` support enabled)  

7. **Implement structured logging** (`src/core/logging.py`)  
   - `structlog` pipeline: JSON in production, pretty in dev  
   - Context vars for `request_id`, `path`, `format`  

**Milestone:** `pytest` green. `from mcp_file_server import app` imports without error.

---

## 3. Phase 1 — MVP Parsers (Days 4–10)

**Goal:** `read_file` tool works for PDF, DOCX, XLSX, CSV with Markdown output.

### Steps:

#### 3.1 PDF Parser (`src/parsers/pdf_parser.py`)

1. Open document with `fitz.open(path)`  
2. Iterate pages; call `page.get_text("blocks")` for layout-ordered blocks  
3. Classify each block: heading (large font size), paragraph, list item  
4. Extract images: `page.get_images(full=True)` → `doc.extract_image(xref)` → `ImageRef`  
5. For each page, attempt table extraction with `pdfplumber.open(path).pages[i].extract_tables()`  
6. Map raw cell arrays to `TableResult` + confidence scoring  
7. Assemble `Section` list preserving document order  
8. Return `ParseResult`  

Edge cases to handle:
- Encrypted PDF: attempt open without password; on error return `ParseError(code="encrypted")`  
- Scanned PDF (image-only): detect via `page.get_text()` returning empty; set `description_hint="Scanned page — OCR required"` for each page image  
- Rotated pages: normalise rotation via `page.rotation`  

#### 3.2 DOCX Parser (`src/parsers/docx_parser.py`)

1. `doc = docx.Document(path)`  
2. Iterate `doc.paragraphs` and `doc.tables` in document order via XML traversal (not separate lists — they interleave in the XML)  
3. For paragraphs: detect heading level from `paragraph.style.name` (e.g. `"Heading 1"`)  
4. For tables: iterate rows/cells; detect header row via first-row style  
5. Extract inline images from `doc.inline_shapes` (type `PICTURE`)  
6. Extract metadata from `doc.core_properties`  

**Critical:** Use `doc.element.body` XML traversal to preserve paragraph/table interleaving:
```python
from docx.oxml.ns import qn
for child in doc.element.body:
    tag = child.tag
    if tag == qn("w:p"):
        # paragraph
    elif tag == qn("w:tbl"):
        # table
```

#### 3.3 XLSX Parser (`src/parsers/xlsx_parser.py`)

1. Use openpyxl `load_workbook(path, read_only=False, data_only=True)`  
2. `data_only=True` returns cached formula values (not formula strings)  
3. For each worksheet: iterate rows, build `TableResult` per sheet  
4. Handle merged cells: `ws.merged_cells.ranges` → expand into `TableCell.rowspan/colspan`  
5. Named ranges: expose via metadata  
6. For large files (> 10MB): use `read_only=True` mode; merged cell info unavailable (note in errors)  

#### 3.4 CSV Parser (`src/parsers/csv_parser.py`)

1. Detect encoding with `chardet.detect(raw_bytes)` on first 4096 bytes  
2. Detect delimiter with `csv.Sniffer().sniff(sample)`  
3. Use `polars.read_csv(path, encoding=detected, separator=detected_delim, infer_schema_length=0)` (all strings — no type coercion that could lose data)  
4. First row as headers unless `has_header=False` option  
5. Build single `TableResult`  

#### 3.5 Markdown Serialiser (`src/serialisers/markdown.py`)

1. Emit YAML front-matter from `DocumentMetadata`  
2. Iterate `sections[]` in order  
3. Dispatch by `SectionType`: heading → ATX, paragraph → plain, table → GFM, image → data URI, code → fenced  
4. Append `<!-- parse_error: ... -->` for each error  
5. Unit tests: assert heading levels, table pipe format, image data URI format  

#### 3.6 FastMCP app + `read_file` tool (`src/app.py`)

1. `mcp = FastMCP("Parsival")`  
2. Define `read_file` tool with Pydantic input/output types  
3. Wire: router → parser → post-processor → serialiser → return  
4. Integration test: call tool via stdio transport, assert Markdown output structure  

#### 3.7 In-Memory Cache (`src/core/cache.py`)

1. SHA-256 of file bytes as primary key  
2. Cache key suffix = `output_format:page_range:include_images`  
3. `cachetools.LRUCache` with byte-size-aware `getsizeof`  
4. Thread-safe via `threading.Lock` (the executor threads write from background processes)  

**Milestone (MVP):** Agent can call `read_file("/path/to/doc.pdf", output_format="markdown")` and receive structured Markdown with sections, tables, and images. Cache works on second call. All unit tests pass.

---

## 4. Phase 2 — Remaining Parsers (Days 11–17)

**Goal:** Full format coverage.

### Steps:

1. **DOC Parser** (`src/parsers/doc_parser.py`)  
   - LibreOffice subprocess: `soffice --headless --convert-to docx --outdir /tmp input.doc`  
   - Wrap in `asyncio.create_subprocess_exec` with `SUBPROCESS_TIMEOUT_SEC` timeout  
   - On success: call `DocxParser` on the converted file  
   - On failure/timeout: `SIGKILL` subprocess, raise `SubprocessError`  
   - Keep LibreOffice process warm (UNO bridge or simply accept ~300ms per conversion)  
   - Semaphore: `asyncio.Semaphore(MAX_LIBREOFFICE_WORKERS)`  

2. **PPTX Parser** (`src/parsers/pptx_parser.py`)  
   - `prs = pptx.Presentation(path)`  
   - Per slide: iterate `slide.shapes` in Z-order  
   - Shape types: `MSO_SHAPE_TYPE.TEXT_BOX`, `TABLE`, `PICTURE`, `PLACEHOLDER`  
   - For text: extract runs preserving bold/italic as Markdown (`**bold**`, `*italic*`)  
   - For tables: `shape.table` → `TableResult`  
   - For pictures: `shape.image.blob` → `ImageRef`  
   - Notes: `slide.notes_slide.notes_text_frame.text`  
   - Section per slide: `type=HEADING`, `content="Slide {n}: {title}"`, `notes=...`  

3. **HTML Parser** (`src/parsers/html_parser.py`)  
   - Parse with `BeautifulSoup(html, "lxml")`  
   - Extract `<title>`, `<meta name="author">` for metadata  
   - Extract tables via `bs4` → `TableResult`  
   - Extract `<img>` tags: if `src` is a data URI, decode; if URL, skip (return `description_hint` only)  
   - Convert body to Markdown via `markdownify.markdownify(str(body), heading_style="ATX")`  

4. **Plain Text / Markdown Parser** (`src/parsers/text_parser.py`)  
   - Read file with detected encoding  
   - If `.md`/`.markdown`: parse with `markdown-it-py` to extract heading structure  
   - Otherwise: single paragraph section with raw text  
   - No image or table extraction (return empty lists)  

5. **Post-Processor: ImageExtractor** (`src/post_processors/image_extractor.py`)  
   - Resize: `Pillow.Image.open(BytesIO(raw_bytes)).thumbnail((max_dim, max_dim), LANCZOS)`  
   - Strip EXIF: `image_copy = Image.new(img.mode, img.size); image_copy.putdata(list(img.getdata()))`  
   - Encode: `base64.b64encode(output_bytes).decode("ascii")`  
   - Infer `description_hint` per strategy in `03_Data_Contracts.md`  

6. **Post-Processor: TableNormaliser** (`src/post_processors/table_normaliser.py`)  
   - Compute confidence score per scoring table in `03_Data_Contracts.md`  
   - Generate `table.markdown` via `to_gfm_table()`  
   - Flatten merged cells into `rows` grid  

7. **Post-Processor: MetadataEnricher** (`src/post_processors/metadata_enricher.py`)  
   - Count words: `sum(len(s.content.split()) for s in sections)`  
   - `reading_time_minutes = word_count / 200`  
   - Build TOC from heading sections  
   - `has_toc`: True if at least 3 headings exist  

**Milestone:** All 8 formats parse successfully. PPTX, DOC, HTML, plain text coverage complete.

---

## 5. Phase 3 — Remaining Tools + JSON Output (Days 18–22)

### Steps:

1. **JSON Serialiser** (`src/serialisers/json_serialiser.py`)  
   - `ParseResult.model_dump_json(indent=2, exclude_none=True)`  
   - Streaming variant: emit metadata first, then sections one at a time  

2. **`get_metadata` tool**  
   - Call `parser.parse_metadata(path)` — must be cheap (open file, read headers only)  
   - PDF: `fitz.open(path).metadata` + page count — no page rendering  
   - DOCX: `doc.core_properties` — no paragraph iteration  
   - XLSX: `wb.properties` — no sheet reading  
   - Return `DocumentMetadata` directly (no `ParseResult` envelope)  

3. **`extract_table` tool**  
   - For XLSX: target specific sheet + table index  
   - For PDF/DOCX: target table by index across full document  
   - Return `TableResult` with `markdown` and `cells` populated  

4. **`extract_images` tool**  
   - Return `list[ImageRef]` without section context  
   - Supports `page_range` filter  
   - Supports `max_dimension` override per call  

5. **`convert_to_markdown` tool**  
   - Thin wrapper around `read_file(..., output_format="markdown")`  
   - Returns `str` directly (no envelope) — convenience for agents that just want Markdown  

6. **`search_file` tool**  
   - After full parse, build BM25 index over section content strings  
   - Return `list[SearchHit]` with snippet and score  
   - Use `rank_bm25` library: `BM25Okapi([s.content.split() for s in sections])`  

**Milestone:** All 6 tools functional. JSON output validated against schema.

---

## 6. Phase 4 — Streaming (Days 23–26)

### Steps:

1. Implement `BaseParser.stream_sections()` native override for PDF  
   - Use `fitz` page-by-page generator: yield one `Section` per page  
   - Do not buffer entire document  

2. Implement streaming in `read_file` when `stream=True`  
   - Wrap `parser.stream_sections()` in `StreamingChunkEmitter`  
   - Emit `StreamChunk` per section  
   - Final chunk: set `is_final=True`, include accumulated `metadata`  

3. FastMCP streaming registration  
   - Change return type to `AsyncGenerator[StreamChunk, None]`  
   - Verify SSE transport delivers chunks incrementally  

4. Backpressure: `asyncio.Queue(maxsize=8)` between parser and emitter  

5. Integration test: stream a 50-page PDF; assert chunks arrive before full document processed  

---

## 7. Phase 5 — Hardening + Benchmarks (Days 27–35)

### Steps:

1. **Edge case handling** per `08_Edge_Cases.md`  
2. **Redis cache backend** (`src/core/cache_redis.py`)  
   - Key: `f"mcp-fs:{cache_key}"`  
   - Value: msgpack-serialised `ParseResult`  
   - `SETEX` with TTL  
3. **ProcessPoolExecutor integration**  
   - Wrap CPU-bound parsers: `await loop.run_in_executor(pool, parse_fn, path, options)`  
   - Pool size = `PROCESS_POOL_SIZE` (default 4)  
4. **Benchmark suite** (`tests/benchmarks/`)  
   - Baseline: PDF 50 pages, DOCX 100 pages, XLSX 10k rows, PPTX 30 slides  
   - Assert: PDF p95 < 2s, DOCX p95 < 1s, XLSX 10k rows p95 < 500ms  
5. **Docker packaging** (`Dockerfile`, `docker-compose.yml`)  
6. **README** with quickstart, tool reference, configuration reference  

**Milestone V1:** Production-ready. All formats, all tools, streaming, Redis cache, Docker.

---

## 8. Milestones Summary

| Milestone | Target | Deliverable |
|-----------|--------|-------------|
| MVP | Day 10 | `read_file` for PDF/DOCX/XLSX/CSV, Markdown output, LRU cache |
| Phase 2 | Day 17 | All 8 formats |
| Phase 3 | Day 22 | All 6 tools, JSON output |
| V1 | Day 26 | Streaming, all tools, production quality |
| V2 | Day 35 | Redis, benchmarks, Docker, OCR plugin hook |

---

## 9. Component Dependencies

```
Config ──────────────────────────────────────┐
                                              │
Models ──► BaseParser ──► ParserRegistry      │
              │                │              │
              │           [PDF, DOCX,         │
              │            XLSX, CSV,         │
              │            DOC, PPTX,         │
              │            HTML, Text]        │
              │                │              │
FormatRouter──┘           PostProcessors      │
              │            (Image, Table,     │
              │             Metadata)         │
              │                │              │
CacheLayer────┤           Serialisers         │
              │            (MD, JSON, Text,   │
              │             Streaming)        │
              │                │              │
              └────► FastMCP Tools ◄──────────┘
```
