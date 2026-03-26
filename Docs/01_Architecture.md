# 01 — System Architecture

## 1. Overview

This document describes the end-to-end architecture of a high-performance FastMCP server that parses multi-format files (PDF, DOCX, DOC, PPTX, XLSX, CSV, HTML, TXT, MD) and emits LLM-optimised structured output (Markdown + JSON). The system is designed for near-zero latency in developer workflows, replacing subprocess-heavy CLI approaches used by coding agents.

---

## 2. Design Principles

| Principle | Implication |
|-----------|-------------|
| Parse once, serve many | Content-hash cache eliminates repeat work |
| Fail explicitly, recover gracefully | Every parser returns a typed `ParseResult` with `confidence` and `errors[]` |
| Composition over monolith | Each format is an independent plugin; the router delegates, never controls |
| Streaming-first | Large files emit sections incrementally; callers are never blocked for full document load |
| Metadata before content | Cheap `get_metadata()` lets agents decide whether a full parse is warranted |
| LLM-first output | Output is structurally optimised for tokeniser efficiency and context window management |

---

## 3. High-Level Component Map

```
┌─────────────────────────────────────────────────────────────┐
│                        MCP CLIENTS                          │
│        (Cursor / VSCode Agent / Claude / any MCP host)      │
└────────────────────────────┬────────────────────────────────┘
                             │  MCP Protocol (JSON-RPC 2.0 / stdio / SSE)
┌────────────────────────────▼────────────────────────────────┐
│                     FASTMCP LAYER                           │
│  Tool registry · Schema validation · Streaming adapter      │
│  Tools: read_file · get_metadata · extract_table ·          │
│         extract_images · convert_to_markdown · search_file  │
└──────────┬──────────────────────────────┬───────────────────┘
           │                              │
┌──────────▼──────────┐       ┌───────────▼──────────────────┐
│   CACHE LAYER       │       │      FORMAT ROUTER           │
│ ContentHashStore    │◄──────│  MIME sniff · ext fallback · │
│ LRU in-process      │  hit  │  magic bytes                 │
│ Optional Redis      │       └───────────┬──────────────────┘
└─────────────────────┘              miss │
                                          │
              ┌───────────────────────────▼──────────────────────────────┐
              │                   PARSER REGISTRY                        │
              │                                                           │
              │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐  │
              │  │ PDF      │  │ Word     │  │ Sheets   │  │  PPTX   │  │
              │  │ Parser   │  │ Parser   │  │ Parser   │  │ Parser  │  │
              │  │(pymupdf) │  │(docx/uno)│  │(openpyxl)│  │(pptx)   │  │
              │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘  │
              │       │             │              │             │        │
              │  ┌────┴─────────────┴──────────────┴─────────────┴─────┐ │
              │  │              COMMON PARSER INTERFACE                 │ │
              │  │   parse(path) → ParseResult                         │ │
              │  │   parse_metadata(path) → DocumentMetadata           │ │
              │  │   stream_sections(path) → AsyncIterator[Section]    │ │
              │  └─────────────────────────────────────────────────────┘ │
              └──────────────────────┬───────────────────────────────────┘
                                     │
              ┌──────────────────────▼───────────────────────────────────┐
              │                POST-PROCESSING PIPELINE                  │
              │                                                           │
              │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
              │  │ Image        │  │ Table        │  │ Metadata      │  │
              │  │ Extractor    │  │ Normaliser   │  │ Enricher      │  │
              │  │ (base64 +    │  │ (GFM + JSON  │  │ (TOC, author, │  │
              │  │  hint)       │  │  confidence) │  │  word count)  │  │
              │  └──────────────┘  └──────────────┘  └───────────────┘  │
              └──────────────────────┬───────────────────────────────────┘
                                     │
              ┌──────────────────────▼───────────────────────────────────┐
              │                  OUTPUT SERIALISERS                      │
              │                                                           │
              │   MarkdownSerializer   ·   JSONSerializer                │
              │   RawTextSerializer    ·   StreamingChunkEmitter          │
              └──────────────────────────────────────────────────────────┘
```

---

## 4. FastMCP Layer

### 4.1 Tool Definitions

All tools are registered with `@mcp.tool()` and expose typed Pydantic schemas that FastMCP converts to JSON Schema for MCP clients.

```
Tool: read_file
  Input:  path: str
          output_format: "markdown" | "json" | "text"  (default: "markdown")
          page_range: [int, int] | None                 (default: None = all)
          include_images: bool                          (default: True)
          max_tokens_hint: int | None                   (default: None)
  Output: ReadFileResult  (see Data Contracts)

Tool: get_metadata
  Input:  path: str
  Output: DocumentMetadata  (cheap — no full parse)

Tool: extract_table
  Input:  path: str
          table_index: int          (default: 0)
          sheet_name: str | None    (XLSX only)
          output_format: "json" | "markdown" | "csv"
  Output: TableResult

Tool: extract_images
  Input:  path: str
          page_range: [int, int] | None
          max_dimension: int        (default: 2048 — rescale if larger)
          format: "png" | "jpeg"    (default: "png")
  Output: list[ImageRef]

Tool: convert_to_markdown
  Input:  path: str
          strict: bool              (default: False — strict disables heuristics)
  Output: str  (pure Markdown — no envelope)

Tool: search_file
  Input:  path: str
          query: str
          top_k: int                (default: 5)
  Output: list[SearchHit]           (section + snippet + offset)
```

### 4.2 Streaming Contract

FastMCP supports `AsyncGenerator` returns for streaming. For large files, `read_file` accepts `stream: bool = False`. When `stream=True`, the tool yields `StreamChunk` objects:

```
StreamChunk {
  chunk_index: int
  total_chunks: int | None   (None if unknown)
  section_type: "heading" | "paragraph" | "table" | "image" | "metadata"
  content: str               (Markdown fragment or JSON fragment)
  is_final: bool
}
```

The MCP client receives server-sent events for each chunk. If the client does not support streaming, fall back to buffered mode automatically.

---

## 5. Format Router

### 5.1 Detection Strategy (three-pass)

```python
def detect_format(path: str) -> FileFormat:
    # Pass 1: magic bytes (most reliable, format-independent)
    mime = magic.from_file(path, mime=True)
    fmt  = MIME_TO_FORMAT.get(mime)
    if fmt:
        return fmt

    # Pass 2: file extension (fast, covers 95% of clean inputs)
    ext = Path(path).suffix.lower()
    fmt = EXTENSION_TO_FORMAT.get(ext)
    if fmt:
        return fmt

    # Pass 3: content sniffing for text-like formats
    with open(path, "rb") as f:
        head = f.read(512)
    if head.startswith(b"---\n") or head.startswith(b"# "):
        return FileFormat.MARKDOWN
    if b"<html" in head.lower():
        return FileFormat.HTML
    if b"," in head and b"\n" in head:
        return FileFormat.CSV  # loose heuristic; validated by parser

    raise UnsupportedFormatError(path=path, detected_mime=mime)
```

### 5.2 Format → Parser Mapping

| Format | Magic bytes / MIME | Parser class |
|--------|--------------------|--------------|
| PDF | `%PDF` / `application/pdf` | `PDFParser` |
| DOCX | PK + `word/` in ZIP / `application/vnd.openxmlformats...` | `DocxParser` |
| DOC | `\xD0\xCF\x11\xE0` / `application/msword` | `DocParser` (LibreOffice subprocess) |
| PPTX | PK + `ppt/` in ZIP | `PptxParser` |
| XLSX | PK + `xl/` in ZIP | `XlsxParser` |
| CSV | text/csv, `.csv` ext | `CsvParser` |
| HTML | `text/html` | `HtmlParser` |
| TXT/MD | `text/plain` | `PlainTextParser` |

---

## 6. Parser Registry

### 6.1 Design Pattern

The registry is a dictionary mapping `FileFormat → BaseParser` instances. Parsers are registered at module import time via a decorator.

```python
# base_parser.py
class BaseParser(ABC):
    @abstractmethod
    async def parse(self, path: Path, options: ParseOptions) -> ParseResult: ...

    @abstractmethod
    async def parse_metadata(self, path: Path) -> DocumentMetadata: ...

    async def stream_sections(
        self, path: Path, options: ParseOptions
    ) -> AsyncIterator[Section]:
        # Default: parse fully, then yield sections
        result = await self.parse(path, options)
        for section in result.sections:
            yield section

    def supports_streaming(self) -> bool:
        return False  # Override to True in parsers that support native streaming

# registry.py
_REGISTRY: dict[FileFormat, BaseParser] = {}

def register(fmt: FileFormat):
    def decorator(cls: Type[BaseParser]) -> Type[BaseParser]:
        _REGISTRY[fmt] = cls()
        return cls
    return decorator

def get_parser(fmt: FileFormat) -> BaseParser:
    parser = _REGISTRY.get(fmt)
    if parser is None:
        raise UnsupportedFormatError(format=fmt)
    return parser
```

### 6.2 Parser Registration Example

```python
# parsers/pdf_parser.py
@register(FileFormat.PDF)
class PDFParser(BaseParser):
    ...
```

---

## 7. Cache Layer

### 7.1 Strategy

Content-hash cache using SHA-256 of the file bytes as the key. Parsed results are stored as msgpack-serialised `ParseResult` objects.

```
cache_key = SHA256(file_bytes) + ":" + serialise(options)
```

Options that affect cache keys: `output_format`, `page_range`, `include_images`, `max_dimension`.

### 7.2 Backends

| Backend | Use Case | Config |
|---------|----------|--------|
| In-process LRU (`cachetools.LRUCache`) | Default, single-process | `max_size=500MB` |
| Redis | Multi-worker / persistent | `CACHE_BACKEND=redis` env var |
| None | Testing / debugging | `CACHE_BACKEND=none` |

### 7.3 Invalidation

Cache entries are never explicitly invalidated in normal operation — the hash key guarantees freshness. An explicit `invalidate_cache(path)` MCP tool exists for edge cases (e.g. NFS-mounted files where inode mtime is unreliable).

### 7.4 Cache Size Management

```
max_entry_size = 50MB      # single cached parse result
max_total_size = 500MB     # LRU evicts when exceeded
ttl            = 3600s     # optional TTL for Redis backend
```

---

## 8. Post-Processing Pipeline

Each parser returns a raw `ParseResult`. The post-processor applies three independent transformations in sequence:

```
ParseResult (raw)
    │
    ▼
ImageExtractor.run(result)    → attaches base64 + description_hint to each ImageRef
    │
    ▼
TableNormaliser.run(result)   → converts raw cell arrays to GFM / JSON, adds confidence score
    │
    ▼
MetadataEnricher.run(result)  → infers word count, reading time, TOC from section tree
    │
    ▼
ParseResult (enriched)
```

These processors are stateless and pure — they do not mutate the input; they return a new `ParseResult`.

---

## 9. Output Serialisers

### 9.1 MarkdownSerializer

Traverses `ParseResult.sections[]` in order and emits a single Markdown string following the strict format spec in `03_Data_Contracts.md`.

Critical rules:
- Headings use ATX style (`#`, `##`, etc.) — no Setext underlines.
- Tables always emit GFM pipe tables with alignment markers.
- Images emit as `![{description_hint}](data:image/{fmt};base64,{b64})`.
- Metadata front-matter is emitted as YAML fenced block at top.
- Code blocks preserve original language hint if available.
- Confidence < 0.6 tables are wrapped in an HTML comment `<!-- low-confidence table -->`.

### 9.2 JSONSerializer

Emits the `ParseResult` Pydantic model as JSON using `.model_dump_json()`. Schema defined in `03_Data_Contracts.md`.

### 9.3 Streaming Emitter

Wraps either serialiser and yields `StreamChunk` objects. Implements backpressure via `asyncio.Queue(maxsize=8)` — the parser is paused if the client is not consuming fast enough.

---

## 10. Data Flow (Sequence)

```
Agent                FastMCP             Router      Cache     Parser     Post-proc
  │                     │                  │           │          │           │
  │ read_file(path,     │                  │           │          │           │
  │   format="md")      │                  │           │          │           │
  │────────────────────►│                  │           │          │           │
  │                     │ detect_format()  │           │          │           │
  │                     │─────────────────►│           │          │           │
  │                     │◄─────────────────│           │          │           │
  │                     │ cache_get(key)   │           │          │           │
  │                     │────────────────────────────►│           │           │
  │                     │ HIT ────────────────────────◄│           │           │
  │◄────────────────────│                  │           │          │           │
  │    (return cached)  │                  │           │          │           │
  │                     │                  │           │          │           │
  │ [cache miss path]   │                  │           │          │           │
  │                     │ get_parser(fmt)  │           │          │           │
  │                     │─────────────────►│           │          │           │
  │                     │ parser.parse()   │           │          │           │
  │                     │──────────────────────────────────────►│           │
  │                     │                  │           │          │           │
  │                     │ post_process()   │           │          │           │
  │                     │────────────────────────────────────────────────►│ │
  │                     │◄───────────────────────────────────────────────── │
  │                     │ serialize(md)    │           │          │           │
  │                     │ cache_set(key)   │           │          │           │
  │                     │────────────────────────────►│           │           │
  │◄────────────────────│                  │           │          │           │
  │  ReadFileResult     │                  │           │          │           │
```

---

## 11. Failure Handling Strategy

### 11.1 Error Taxonomy

| Error Class | Description | Recovery |
|-------------|-------------|----------|
| `UnsupportedFormatError` | Format not in registry | Return error `ParseResult` with `status="unsupported"` |
| `ParseError` | Parser threw exception | Return partial result with `status="partial"`, populate `errors[]` |
| `CorruptFileError` | File unreadable / truncated | Return `status="failed"`, `errors[0].code="corrupt"` |
| `SubprocessError` | LibreOffice timeout / crash | Retry once with 5s timeout; if fails, return `status="failed"` |
| `OversizeError` | File exceeds `MAX_FILE_SIZE` | Return `status="oversize"` with `metadata.size_bytes` |
| `EncodingError` | Text with unknown encoding | Detect with `chardet`, fallback to `latin-1` with `errors="replace"` |

### 11.2 Never Raise to Client

All errors are **caught inside the parser** and encoded in `ParseResult.errors[]`. The MCP tool layer never raises an unhandled exception — callers always receive a typed result. This ensures coding agents do not need `try/except` around every call.

### 11.3 Partial Success

If a 50-page PDF has one corrupted page, the parser yields sections for all other pages and adds an `errors` entry: `{"page": 12, "code": "render_failed", "message": "..."}`. The overall `status` is `"partial"`.

### 11.4 LibreOffice Watchdog

LibreOffice subprocess conversions are wrapped in an asyncio timeout (`SUBPROCESS_TIMEOUT_SEC=30`). A watchdog task monitors the process; if it exceeds the timeout, `SIGKILL` is sent and a `SubprocessError` is raised internally.

---

## 12. Scalability Considerations

| Concern | Design Decision |
|---------|-----------------|
| Single-process FastMCP | Async I/O throughout; parser I/O is non-blocking |
| CPU-bound parsing | Offloaded to `ProcessPoolExecutor` (configurable pool size) |
| LibreOffice concurrency | Semaphore limits concurrent LibreOffice processes to `MAX_LIBREOFFICE_WORKERS=2` |
| Large file memory | Files > `STREAM_THRESHOLD_MB=10` use streaming parse paths |
| Multi-worker deploy | Redis cache backend enables shared state across workers |
| Rate limiting | Token bucket per client-ID via MCP metadata (opt-in) |

---

## 13. Configuration Reference

All configuration is read from environment variables with sane defaults, validated on startup via Pydantic `BaseSettings`.

```
MCP_HOST                = "0.0.0.0"
MCP_PORT                = 8765
CACHE_BACKEND           = "memory"         # memory | redis | none
CACHE_MAX_MB            = 500
CACHE_TTL_SEC           = 3600
REDIS_URL               = "redis://localhost:6379/0"
MAX_FILE_SIZE_MB        = 500
STREAM_THRESHOLD_MB     = 10
MAX_LIBREOFFICE_WORKERS = 2
SUBPROCESS_TIMEOUT_SEC  = 30
IMAGE_MAX_DIMENSION     = 2048
LOG_LEVEL               = "INFO"
SENTRY_DSN              = ""               # optional
PROCESS_POOL_SIZE       = 4
```
