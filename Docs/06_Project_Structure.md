# 06 — Project Structure

## 1. Full Folder Layout

```
Parsival/
│
├── src/
│   ├── __init__.py
│   ├── app.py                          # FastMCP app entry point
│   ├── config.py                       # Pydantic BaseSettings
│   │
│   ├── models/                         # Pydantic data models (no logic)
│   │   ├── __init__.py
│   │   ├── enums.py                    # FileFormat, ParseStatus, SectionType, OutputFormat
│   │   ├── metadata.py                 # TOCEntry, DocumentMetadata
│   │   ├── image.py                    # ImageRef
│   │   ├── table.py                    # TableCell, TableResult
│   │   ├── parse_result.py             # ParseError, Section, ParseResult
│   │   └── tool_responses.py           # ReadFileResult, StreamChunk, SearchHit
│   │
│   ├── core/                           # Infrastructure (no format-specific logic)
│   │   ├── __init__.py
│   │   ├── logging.py                  # structlog pipeline
│   │   ├── router.py                   # FormatRouter (magic bytes / ext / sniff)
│   │   ├── cache.py                    # ContentHashStore (LRU, in-memory)
│   │   ├── cache_redis.py              # RedisContentHashStore
│   │   └── cache_factory.py            # Build correct backend from Settings
│   │
│   ├── parsers/                        # One file per format
│   │   ├── __init__.py
│   │   ├── base.py                     # BaseParser ABC
│   │   ├── registry.py                 # ParserRegistry + @register decorator
│   │   ├── pdf_parser.py               # PyMuPDF + pdfplumber
│   │   ├── docx_parser.py              # python-docx
│   │   ├── doc_parser.py               # LibreOffice subprocess → DocxParser
│   │   ├── pptx_parser.py              # python-pptx
│   │   ├── xlsx_parser.py              # openpyxl + polars
│   │   ├── csv_parser.py               # polars + chardet
│   │   ├── html_parser.py              # bs4 + lxml + markdownify
│   │   └── text_parser.py              # plain text + markdown-it-py
│   │
│   ├── post_processors/                # Stateless enrichment pipeline
│   │   ├── __init__.py
│   │   ├── image_extractor.py          # Resize, EXIF strip, base64, hint inference
│   │   ├── table_normaliser.py         # Confidence scoring, GFM gen, cell flattening
│   │   ├── metadata_enricher.py        # Word count, reading time, TOC
│   │   └── pipeline.py                 # Compose all three processors
│   │
│   ├── serialisers/                    # Convert ParseResult to output formats
│   │   ├── __init__.py
│   │   ├── markdown.py                 # MarkdownSerializer
│   │   ├── json_serialiser.py          # JSONSerializer
│   │   ├── text_serialiser.py          # RawTextSerializer
│   │   └── streaming.py               # StreamingChunkEmitter
│   │
│   └── tools/                          # FastMCP tool definitions (thin wrappers)
│       ├── __init__.py
│       ├── read_file.py
│       ├── get_metadata.py
│       ├── extract_table.py
│       ├── extract_images.py
│       ├── convert_to_markdown.py
│       ├── search_file.py
│       └── list_formats.py
│
├── tests/
│   ├── conftest.py                     # Fixtures: sample files, mock parsers
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_router.py
│   │   ├── test_cache.py
│   │   ├── test_markdown_serialiser.py
│   │   ├── test_table_normaliser.py
│   │   ├── test_image_extractor.py
│   │   └── test_metadata_enricher.py
│   ├── integration/
│   │   ├── test_pdf_parser.py
│   │   ├── test_docx_parser.py
│   │   ├── test_xlsx_parser.py
│   │   ├── test_csv_parser.py
│   │   ├── test_doc_parser.py          # Requires LibreOffice
│   │   ├── test_pptx_parser.py
│   │   ├── test_html_parser.py
│   │   ├── test_tools.py               # Full tool call via FastMCP test client
│   │   └── test_streaming.py
│   └── benchmarks/
│       ├── bench_pdf.py
│       ├── bench_docx.py
│       ├── bench_xlsx.py
│       └── bench_pptx.py
│
├── fixtures/                           # Test sample files (committed to repo)
│   ├── sample.pdf                      # 5-page PDF with tables and images
│   ├── sample.docx
│   ├── sample.doc
│   ├── sample.pptx
│   ├── sample.xlsx
│   ├── sample.csv
│   ├── sample.html
│   └── sample.md
│
├── scripts/
│   ├── generate_fixtures.py            # Creates sample files for testing
│   └── warm_libreoffice.py             # Pre-warms LibreOffice subprocess
│
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
└── README.md
```

---

## 2. Module Responsibilities

### `src/app.py`

The sole entry point. Responsibilities:
- Instantiate `FastMCP` app
- Import and register all tools from `src/tools/`
- On startup: initialise `ProcessPoolExecutor`, warm LibreOffice, init cache
- On shutdown: shutdown pool, flush Redis if applicable
- Register error handler: convert unhandled exceptions to MCP error responses

```python
# src/app.py (sketch)
from fastmcp import FastMCP
from src.config import settings
from src.tools import read_file, get_metadata, extract_table, extract_images, \
                      convert_to_markdown, search_file, list_formats

mcp = FastMCP("Parsival", version="1.0.0")

mcp.add_tool(read_file.tool)
mcp.add_tool(get_metadata.tool)
# ... etc

@mcp.on_startup
async def startup():
    await init_cache(settings)
    await warm_libreoffice()
    init_process_pool(settings.PROCESS_POOL_SIZE)
```

---

### `src/config.py`

Reads all configuration from environment variables. Validates on import. Exposes a singleton `settings` object.

Key conventions:
- All env vars are prefixed with `MCP_` to avoid collisions
- Default values are set for all non-secret fields
- Secret fields (`REDIS_URL`, `SENTRY_DSN`) default to `None` — features are disabled if not set

---

### `src/models/` — Data Models

**No logic here.** All models are pure Pydantic data containers. Computed fields (like `ImageRef.data_uri`) are allowed as they are declarative and have no side effects.

Naming convention:
- Model classes: PascalCase
- Enum values: UPPER_SNAKE_CASE
- Field names: snake_case

---

### `src/parsers/base.py` — BaseParser

```python
class BaseParser(ABC):
    """
    All methods are async to support:
    1. Async file I/O (via anyio)
    2. Running blocking calls in ProcessPoolExecutor
    3. Awaiting LibreOffice subprocess
    """

    @abstractmethod
    async def parse(self, path: Path, options: ParseOptions) -> ParseResult:
        """Full document parse. Returns enriched ParseResult."""
        ...

    @abstractmethod
    async def parse_metadata(self, path: Path) -> DocumentMetadata:
        """Cheap metadata-only extraction. No page rendering, no image extraction."""
        ...

    async def stream_sections(
        self, path: Path, options: ParseOptions
    ) -> AsyncIterator[Section]:
        """Default: buffer full parse then yield. Override for native streaming."""
        result = await self.parse(path, options)
        for section in result.sections:
            yield section

    def supports_streaming(self) -> bool:
        return False
```

---

### `src/parsers/registry.py` — Registry

The registry is a module-level singleton. Parsers self-register at import time.

```python
_REGISTRY: dict[FileFormat, BaseParser] = {}

def register(fmt: FileFormat):
    def decorator(cls: Type[BaseParser]) -> Type[BaseParser]:
        instance = cls()
        _REGISTRY[fmt] = instance
        return cls
    return decorator
```

All parser modules are imported in `src/parsers/__init__.py` to trigger registration:

```python
# src/parsers/__init__.py
from . import pdf_parser, docx_parser, doc_parser, pptx_parser, \
              xlsx_parser, csv_parser, html_parser, text_parser
```

---

### `src/tools/` — Tool Definitions

Each tool file exports a single `tool` object (FastMCP `Tool` instance). Thin wrappers — no business logic. All logic lives in parsers, post-processors, and serialisers.

```python
# src/tools/read_file.py
from fastmcp import Tool
from src.core.router import FormatRouter
from src.core.cache import get_cache
from src.parsers.registry import get_parser
from src.post_processors.pipeline import PostProcessingPipeline
from src.serialisers.markdown import MarkdownSerializer
from src.models.tool_responses import ReadFileResult

async def _read_file(
    path: str,
    output_format: OutputFormat = OutputFormat.MARKDOWN,
    page_range: list[int] | None = None,
    include_images: bool = True,
    max_tokens_hint: int | None = None,
    stream: bool = False,
) -> ReadFileResult:
    fmt    = FormatRouter().detect(path)
    parser = get_parser(fmt)
    cache  = get_cache()

    options = ParseOptions(
        output_format=output_format,
        page_range=tuple(page_range) if page_range else None,
        include_images=include_images,
    )
    cache_key = cache.make_key(path, options)

    if cached := await cache.get(cache_key):
        return serialise(cached, output_format, cache_hit=True)

    result  = await parser.parse(Path(path), options)
    result  = PostProcessingPipeline().run(result)
    await cache.set(cache_key, result)

    return serialise(result, output_format, cache_hit=False)

tool = Tool.from_function(_read_file, name="read_file", description="...")
```

---

## 3. Naming Conventions

| Artifact | Convention | Example |
|----------|-----------|---------|
| Classes | PascalCase | `PDFParser`, `TableResult` |
| Functions / methods | snake_case | `parse_metadata`, `to_gfm_table` |
| Constants | UPPER_SNAKE_CASE | `MAX_FILE_SIZE_MB` |
| Pydantic fields | snake_case | `file_size_bytes` |
| Enum values | UPPER_SNAKE_CASE | `FileFormat.DOCX` |
| Test files | `test_<module>.py` | `test_pdf_parser.py` |
| Fixture files | descriptive, no spaces | `sample_with_tables.pdf` |
| Environment vars | `MCP_` prefix | `MCP_CACHE_MAX_MB` |

---

## 4. Parser Plugin Architecture

New parsers can be added without modifying any existing code:

1. Create `src/parsers/new_format_parser.py`
2. Decorate with `@register(FileFormat.NEW_FORMAT)`
3. Add `FileFormat.NEW_FORMAT` to the `FileFormat` enum
4. Add MIME/extension mapping to `FormatRouter`
5. Import in `src/parsers/__init__.py`

The tool layer, cache, post-processors, and serialisers all work unchanged. This is the open/closed principle: open for extension, closed for modification.

---

## 5. Test Fixture Strategy

All test fixtures are real files committed to the `fixtures/` directory. They are small (< 500KB each) but contain the full range of features:

| Fixture | Key features |
|---------|-------------|
| `sample.pdf` | 5 pages, 2 images, 1 table, headings H1–H3 |
| `sample.docx` | Inline image, merged table, tracked changes (to test XML traversal) |
| `sample.xlsx` | 3 sheets, merged cells, named range, formula values |
| `sample.pptx` | 5 slides: text, table, image, notes, master layout |
| `sample.csv` | UTF-8 with quoted fields, embedded commas |
| `sample_latin1.csv` | Latin-1 encoding (tests encoding detection) |
| `sample.html` | Title meta, `<table>`, `<img>` with data URI, external image |
| `sample.md` | H1–H4 headings, fenced code, GFM table |

The `scripts/generate_fixtures.py` script recreates all fixtures programmatically, so they can be regenerated after format library upgrades.
