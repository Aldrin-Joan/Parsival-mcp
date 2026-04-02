# 05 — Tasks TODO

**Legend:**  
`[E]` Easy (< 1hr) · `[M]` Medium (1–4hr) · `[H]` Hard (> 4hr)  
`deps:` = task IDs that must be complete first

---

## Phase 0 — Foundations (Completed)

### P0-01: Project scaffold `[E]` ✅
- Create `src/`, `tests/`, `scripts/`, `docs/` directories
- Create `pyproject.toml` with all dependencies from `02_Tech_Stack.md`
- Configure `ruff` (linter), `mypy` (type checker), `pytest` with `pytest-asyncio`
- Create `src/__init__.py`, `src/models/__init__.py`, etc.
- deps: none

### P0-02: Enums `[E]` ✅
- Create `src/models/enums.py`
- Define: `FileFormat`, `OutputFormat`, `ParseStatus`, `SectionType`
- Write `tests/unit/test_enums.py`: instantiation, serialisation
- deps: P0-01

### P0-03: Metadata model `[E]` ✅
- Create `src/models/metadata.py`
- Define: `TOCEntry`, `DocumentMetadata`
- Write unit tests: instantiation with nulls, JSON round-trip
- deps: P0-02

### P0-04: Image model `[M]` ✅
- Create `src/models/image.py`
- Define: `ImageRef` with `data_uri` computed field
- Verify `data_uri` format in tests
- deps: P0-02

### P0-05: Table models `[M]` ✅
- Create `src/models/table.py`
- Define: `TableCell`, `TableResult`
- Test merged cell edge case: colspan > 1
- deps: P0-02

### P0-06: Section and ParseResult models `[M]` ✅
- Create `src/models/parse_result.py`
- Define: `ParseError`, `Section`, `ParseResult`
- Test: round-trip JSON; verify `sections` ordering
- deps: P0-03, P0-04, P0-05

### P0-07: Tool response models `[E]` ✅
- Create `src/models/tool_responses.py`
- Define: `ReadFileResult`, `StreamChunk`, `SearchHit`
- deps: P0-06

### P0-08: Settings `[M]` ✅
- Create `src/config.py` using `pydantic-settings`
- All env vars from Architecture doc Section 13
- Startup validation: check LibreOffice path, Redis URL if backend=redis
- Test: default values load correctly; env override works
- deps: P0-01

### P0-09: Structured logging `[M]` ✅
- Create `src/core/logging.py`
- Configure `structlog`: JSON renderer in prod, console renderer in dev
- Add context vars: `request_id`, `path`, `format`, `duration_ms`
- Expose `get_logger(name)` helper
- deps: P0-08

### P0-10: BaseParser ABC `[M]` ✅
- Create `src/parsers/base.py`
- Define `BaseParser` with abstract `parse()`, `parse_metadata()`, `stream_sections()`
- Default `stream_sections()`: buffer full parse then yield
- `supports_streaming()` → False (default)
- deps: P0-06

### P0-11: ParserRegistry `[M]` ✅
- Create `src/parsers/registry.py`
- `@register(FileFormat.X)` decorator
- `get_parser(fmt)` with clear error on unknown format
- `list_supported_formats() -> list[FileFormat]`
- Test: register mock parser, retrieve it
- deps: P0-10

### P0-12: FormatRouter `[H]` ✅
- Create `src/core/router.py`
- Three-pass detection: magic bytes (python-magic), extension, content sniff
- Mapping tables: `MIME_TO_FORMAT`, `EXTENSION_TO_FORMAT`
- Unit tests with real sample files for all 8 formats
- Test edge: wrong extension on a DOCX file (magic bytes wins)
- deps: P0-02, P0-08

### P0-13: In-memory cache `[M]` ✅
- Create `src/core/cache.py`
- `ContentHashStore` class: SHA-256 key, LRU eviction
- `cache_key(path, options) -> str`: hash file bytes + serialise options
- `get()`, `set()`, `invalidate()` async methods
- Thread-safe with `threading.Lock`
- Test: cache hit returns same object; eviction works under size limit
- deps: P0-06

---

## Phase 1 — MVP Parsers (Completed) ✅

### P1-01: PDF parser — text extraction `[H]` ✅
- Create `src/parsers/pdf_parser.py`
- Register `@register(FileFormat.PDF)`
- Open with `fitz.open(path)`
- Extract blocks with `page.get_text("dict")` / heuristics for each page
- Classify blocks into `Section` (heading heuristic: font size > body median × 1.3)
- Build `ParseResult` with sections only (no images/tables yet)
- Test with sample PDF; assert section count > 0
- deps: P0-10, P0-11, P0-12

### P1-02: PDF parser — image extraction `[M]` ✅
- Extend `PDFParser`
- `page.get_images(full=True)` per page
- `doc.extract_image(xref)` → raw bytes → `ImageRef`
- Assign `description_hint` from nearest heading section
- Test: extract images from PDF with known image count
- deps: P1-01, P0-04

### P1-03: PDF parser — table extraction `[H]` ✅
- Extend `PDFParser`
- Import `pdfplumber`; open same path in parallel
- Per page: `plumber_page.extract_tables()` → raw cell lists
- Map to `TableResult` with confidence scoring
- Test: PDF with known tables; assert column/row counts
- deps: P1-01, P0-05

### P1-04: PDF metadata `[E]` ✅
- Implement `PDFParser.parse_metadata()`
- `doc = fitz.open(path)`, read `doc.metadata`
- Read page count without rendering: `doc.page_count`
- Return `DocumentMetadata` — no page iteration
- Test: assert metadata fields and page_count
- deps: P1-01

### P1-05: DOCX parser `[H]` ✅
- Create `src/parsers/docx_parser.py`
- XML-order traversal of `doc.element.body`
- Heading detection from `paragraph.style.name`
- Bold/italic preservation: check `run.bold`, `run.italic` → wrap in `**` / `*`
- Table extraction via `docx.table` object
- deps: P0-10, P0-11

### P1-06: DOCX images `[M]` ✅
- Extend `DocxParser`
- `doc.inline_shapes` for inline images
- Relationship part traversal for media blobs
- Test: DOCX with embedded PNG; assert `ImageRef` returned
- deps: P1-05, P0-04

### P1-07: DOCX metadata `[E]` ✅
- Implement `DocxParser.parse_metadata()`
- `doc.core_properties`: title, author, created, modified, last_modified_by
- No paragraph iteration
- deps: P1-05

### P1-08: XLSX parser `[H]` ✅
- Create `src/parsers/xlsx_parser.py`
- `load_workbook(path, data_only=True)`
- Per worksheet: iterate rows, build `TableResult`
- Merged cell expansion: `ws.merged_cells.ranges`
- Large file mode (> 10MB): `read_only=True`, note merged cells unavailable in errors[]
- deps: P0-10, P0-11

### P1-09: XLSX metadata `[E]` ✅
- Implement `XlsxParser.parse_metadata()`
- `wb.properties`: title, creator, modified
- Sheet names as keywords
- deps: P1-08

### P1-10: CSV parser `[M]` ✅
- Create `src/parsers/csv_parser.py`
- Encoding detection: `chardet.detect(first_4096_bytes)`
- Delimiter detection: `csv.Sniffer().sniff(sample)`
- Parse with `polars.read_csv()`, all strings
- Single `TableResult` output
- Test: UTF-8 CSV, Latin-1 CSV, tab-delimited TSV
- deps: P0-10, P0-11

### P1-11: MarkdownSerializer `[H]` ✅
- Create `src/serialisers/markdown.py`
- YAML front-matter from `DocumentMetadata`
- Section dispatch: heading/paragraph/table/image/code/list
- GFM table generation (`to_gfm_table()` per Data Contracts)
- Data URI image embedding
- HTML comment for errors and low-confidence tables
- Unit tests: every `SectionType` covered; table pipe format validated
- deps: P0-06, P0-07

### P1-12: Post-processor — ImageExtractor `[M]` ✅
- Create `src/post_processors/image_extractor.py`
- Resize via Pillow LANCZOS if > `IMAGE_MAX_DIMENSION`
- EXIF strip
- Base64 encode
- `description_hint` inference pipeline
- Test: oversized PNG → assert resized; EXIF stripped
- deps: P0-04

### P1-13: Post-processor — TableNormaliser `[M]` ✅
- Create `src/post_processors/table_normaliser.py`
- Confidence scoring per 03_Data_Contracts table
- GFM table generation
- Merged cell flattening
- Test: confidence scores for known-good and known-bad tables
- deps: P0-05

### P1-14: Post-processor — MetadataEnricher `[E]` ✅
- Create `src/post_processors/metadata_enricher.py`
- Word count, char count, reading time
- TOC construction from heading sections
- `has_toc` flag
- deps: P0-03, P0-06

### P1-15: PostProcessingPipeline `[M]` ✅
- Create `src/post_processors/pipeline.py`
- Compose ImageExtractor → TableNormaliser → MetadataEnricher
- Each processor: pure function, returns new `ParseResult`
- Test: pipeline on full `ParseResult`; assert all fields enriched
- deps: P1-12, P1-13, P1-14

### P1-16: FastMCP app scaffold `[M]` ✅
- Create `src/app.py`
- `mcp = FastMCP("Parsival", version="0.1.0")`
- Startup hook: warm LibreOffice, initialise cache, init process pool
- Shutdown hook: clean up pool
- deps: P0-09, P0-11

### P1-17: `read_file` tool `[M]` ✅
- Define tool in `src/tools/read_file.py`
- Wire: router → cache check → parser → post-processor → serialiser
- Return `ReadFileResult`
- Integration test: call tool via FastMCP test client on sample files
- deps: P1-11, P1-15, P1-16, P0-13

### P1-18: Integration tests `[E]` ✅
- Create `tests/integration/` directory
- Add integration tests for:
  - `read_file` happy path
  - unsupported format path
  - markdown output contract
  - metadata path
- Verify no unit tests removed
- deps: P1-17

---

## Phase 2 — Remaining Formats (Completed) ✅

### P2-01: DOC parser (LibreOffice) `[H]` ✅
- Create `src/parsers/doc_parser.py`
- `asyncio.create_subprocess_exec` for `soffice --headless --convert-to docx`
- Semaphore guard (`MAX_LIBREOFFICE_WORKERS`)
- Timeout watchdog + `SIGKILL`
- On success: delegate to `DocxParser`
- Test: `.doc` file → assert same output as equivalent DOCX
- deps: P1-05, P0-08

### P2-02: PPTX parser `[H]` ✅
- Create `src/parsers/pptx_parser.py`
- Slide-by-slide iteration
- Shape type dispatch: text → Section, table → TableResult, picture → ImageRef
- Bold/italic from run properties
- Notes extraction
- Slide title as heading
- Test: PPTX with text, table, image per slide
- deps: P0-10, P0-11

### P2-03: HTML parser `[M]` ✅
- Create `src/parsers/html_parser.py`

---

## Phase 4 — Streaming / Incremental Parse (Completed) ✅

### P4-01: PDF native streaming `[M]` ✅
- Implement `PDFParser.stream_sections(path, options)`
- page-by-page section emission (no full `ParseResult` pre-buffer)
- `supports_streaming() -> True`
- Add test to assert first section emitted before complete parse

### P4-02: StreamingChunkEmitter `[M]` ✅
- Create `src/parsers/streaming_chunk_emitter.py`
- `asyncio.Queue(maxsize=8)` for backpressure
- emits `StreamChunk` records per section
- final chunk with `is_final=True`, metadata and summary
- test slow consumer / bounded memory

### P4-03: read_file streaming mode `[M]` ✅
- `parse_file(..., stream=True)` path returns `AsyncGenerator[StreamChunk]`
- `src/tools/read_file.py` supports `stream=True` path
- `StreamChunk` final chunk includes metadata
- Integration test via tool with `stream=True` ensures first chunk appears early

- bs4 + lxml backend
- Meta extraction: title, author, description
- Table extraction via bs4
- Inline image handling: data URI decode vs external URL skip
- Body → Markdown via markdownify
- deps: P0-10, P0-11

### P2-04: PlainText / Markdown parser `[E]` ✅
- Create `src/parsers/text_parser.py`
- Encoding detection
- Markdown: parse with markdown-it-py for heading structure
- Plain text: single paragraph section
- deps: P0-10, P0-11

---

## Phase 3 — Remaining Tools (Completed) ✅

### P3-01: JSONSerializer `[M]` ✅
- Create `src/serialisers/json_serialiser.py`
- `ParseResult.model_dump_json(indent=2, exclude_none=True)`
- Streaming variant: emit metadata first, yield sections as JSON fragments
- Test: schema validation of output against JSON Schema
- deps: P0-06

### P3-02: `get_metadata` tool `[M]` ✅
- Create `src/tools/get_metadata.py`
- Cheap parse: call `parser.parse_metadata(path)` directly
- Return `DocumentMetadata` (no `ParseResult`)
- Test: 500-page PDF completes in < 100ms
- deps: P1-04, P1-07, P1-09

### P3-03: `extract_table` tool `[M]` ✅
- Create `src/tools/extract_table.py`
- `table_index` parameter
- `sheet_name` for XLSX
- Return `TableResult` with GFM and JSON representations
- deps: P1-03, P1-08

### P3-04: `extract_images` tool `[M]` ✅
- Create `src/tools/extract_images.py`
- `page_range` filter
- `max_dimension` and `format` per-call override
- Return `list[ImageRef]`
- deps: P1-02, P1-06

### P3-05: `convert_to_markdown` tool `[E]` ✅
- Thin wrapper around `read_file(..., output_format="markdown")`
- Return `str` directly
- deps: P1-17

### P3-06: `search_file` tool `[H]` ✅
- Create `src/tools/search_file.py`
- Build BM25 index from `ParseResult.sections` content
- Use `rank_bm25.BM25Okapi`
- Return `list[SearchHit]` sorted by score
- Add `rank_bm25` to dependencies
- Test: search known string in known document; assert hit in top-3
- deps: P1-17

### P3-07: `list_supported_formats` tool `[E]` ✅
- Return `list[FileFormat]` from registry
- Include current server version in response
- deps: P0-11

---

## Phase 4 — Streaming

### P4-01: PDF native streaming `[H]`
- Override `PDFParser.stream_sections()`
- Yield one `Section` per page without buffering full result
- `supports_streaming()` → True
- Test: mock slow page read; assert first chunk arrives before all pages processed
- deps: P1-01

### P4-02: StreamingChunkEmitter `[M]`
- Create `src/serialisers/streaming.py`
- `asyncio.Queue(maxsize=8)` for backpressure
- Wraps any `AsyncIterator[Section]`
- Yields `StreamChunk` per section
- Final chunk: `is_final=True`, accumulate metadata
- deps: P0-07

### P4-03: `read_file` streaming mode `[M]`
- Add `stream: bool = False` parameter to `read_file`
- When `True`: return `AsyncGenerator[StreamChunk, None]`
- When `False`: existing buffered path
- FastMCP streaming registration
- Integration test: SSE transport delivers chunks before file fully parsed
- deps: P4-01, P4-02

---

## Phase 5 — Hardening ✅

### P5-01: Encrypted PDF handling `[M]` ✅
- Attempt `fitz.open(path)` without password
- On `fitz.FileDataError`: return `ParseResult(status=FAILED, errors=[ParseError(code="encrypted")])`
- deps: P1-01

### P5-02: Corrupt file handling `[M]` ✅
- Wrap all parser `open()` calls in try/except
- On any read error: return `status=FAILED, errors=[ParseError(code="corrupt")]`
- deps: all parsers

### P5-03: Oversize file guard `[E]` ✅
- Check `os.path.getsize(path)` before parsing
- If > `MAX_FILE_SIZE_MB`: return `status=OVERSIZE`
- deps: P0-08

### P5-04: Encoding error recovery `[M]` ✅
- Detect with `chardet` on first 4096 bytes
- If confidence < 0.7: attempt UTF-8, then Latin-1 with `errors="replace"`
- Log warning with detected encoding and confidence
- deps: P1-10

### P5-05: LibreOffice timeout + SIGKILL `[M]` ✅
- `asyncio.wait_for(subprocess_coro, timeout=SUBPROCESS_TIMEOUT_SEC)`
- On `asyncio.TimeoutError`: send `SIGKILL`, raise `SubprocessError`
- Retry once before returning error result
- deps: P2-01

### P5-06: ProcessPoolExecutor integration `[H]` ✅
- Wrap `PDFParser.parse()`, `XlsxParser.parse()` in executor
- `loop.run_in_executor(process_pool, sync_parse_fn, path, options)`
- Parsers must be picklable (no lambda closures, no open file handles passed in)
- Test: assert event loop not blocked during CPU-bound parse
- deps: P1-01, P1-08

### P5-07: Redis cache backend `[M]` ✅
- `ContentHashStore` with Redis optional fallback
- `get/set/invalidate` supports Redis and in-memory fallback
- TTL via `REDIS_TTL`
- Test: cache hit/miss, and failure fallback to memory
- deps: P0-13

### P5-08: Benchmark suite `[H]` ✅
- `tests/benchmarks/` added
- pytest-benchmark scenario: small parse, large parse, stream first chunk, parallel throughput
- Fallback timings when plugin not installed
- deps: all parsers

### P5-09: Docker packaging `[M]` ✅
- Multi-stage `Dockerfile` with LibreOffice, poppler, libmagic, fonts
- `docker-compose.yml` with app + optional redis
- Build/run tested successfully
- deps: P0-08

### P5-10: README and tool reference `[M]` ✅
- README includes setup, usage, architecture, troubleshooting
- deps: all phases complete
