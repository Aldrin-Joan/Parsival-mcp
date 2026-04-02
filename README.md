# Parsival

Parsival is a production-friendly, tool-based file parsing microservice built on FastMCP. It is designed to convert common document formats into rich structured outputs (Markdown, JSON, text), with performance tuning and safety hardening for stream processing and agent integrations.

- Supported input formats: PDF, DOCX, DOC, PPTX, XLSX, CSV, HTML, MD, TXT
- Streaming parse support for large documents
- Cache layer: in-memory LRU + optional Redis
- Robust handling of corrupt/encrypted documents, size limits, subprocess isolation
- Plugin-style parser registry and post-processing pipeline

---

## Table of Contents

1. [Quickstart](#quickstart)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Repository layout](#repository-layout)
5. [Configuration](#configuration)
6. [Local development](#local-development)
7. [Running in Docker](#running-in-docker)
8. [API and tools](#api-and-tools)
9. [Parser details](#parser-details)
10. [Cache behavior](#cache-behavior)
11. [Testing and CI](#testing-and-ci)
12. [Troubleshooting](#troubleshooting)

---

## Quickstart

### Clone repository

```bash
git clone https://github.com/Aldrin-Joan/Parsival-mcp.git
cd Parsival-mcp
```

### Python virtual environment

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Run server

Recommended (local stdio MCP):

```bash
python -m src.mcp_entrypoint
```

This uses `MCP_TRANSPORT=stdio` by default in project tooling and keeps stdout dedicated to MCP protocol traffic.

When to use each transport mode:

- `stdio` (recommended default): local development, VS Code MCP integration, and migration target behavior.
- `fastmcp` SSE/HTTP (legacy rollback): temporary compatibility fallback if a client requires HTTP/SSE transport.

Legacy rollback (FastMCP SSE/HTTP):

```bash
set MCP_TRANSPORT=fastmcp
set FASTMCP_SERVER_HOST=0.0.0.0
set FASTMCP_SERVER_PORT=8000
python -m src.mcp_entrypoint
```

or using legacy FastMCP command directly:

```bash
python -m fastmcp --host 0.0.0.0 --port 8000 --transport sse src/app.py:mcp
```

### Verify supported formats

```python
from src.app import list_supported_formats
print(list_supported_formats())
```

---

## Features

- Multi-format file parsing with dedicated parser plugins
- Output in Markdown, JSON, or raw text
- Streaming parser mode (`stream=True`) for early chunks
- Redis-backed caching with local LRU fallback
- Configurable file-size caps and parser timeouts
- LibreOffice conversion path for `.doc` support
- In-process and worker process isolation via `ProcessPoolExecutor`
- Rich `ParseResult` model with metadata, errors, and recoverability flags
- Pluggable post-processing pipeline: metadata enrichment, table normalization, image extraction

---

## Architecture

### Logical layers

- `src/app.py` - FastMCP app & tool definitions
- `src/core` - configuration, caching, routing, executor, security
- `src/parsers` - format-specific parsing logic
- `src/post_processors` - result enrichment pipeline
- `src/serialisers` - output marshal (Markdown, JSON, text)
- `src/tools` - public tool API bound to FastMCP

### Core flow

1. Client calls MCP tool (e.g., `read_file`).
2. `src/tools/read_file.py` validates path via `validate_safe_path()`.
3. `src.app.parse_file()` uses `FormatRouter` to infer `FileFormat`.
4. parser fetched from `src.parsers.registry`.
5. `core.executor.run_parse_in_pool()` executes parser in process pool.
6. `PostProcessingPipeline` normalizes output.
7. Cache key is generated in `ContentHashStore` from file hash + options.
8. Serialized response returned.

### Format detection (router)

- `magic` MIME sniff (if available)
- extension map (e.g., `.pdf`, `.docx`, `.pptx`)
- content heuristics for CSV/HTML/Markdown

### Supported tools

- `read_file`
- `get_metadata`
- `extract_table`
- `extract_images`
- `convert_to_markdown`
- `search_file`
- `list_supported_formats`

---

## Repository layout

```
.
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── src/
│   ├── app.py
│   ├── config.py
│   ├── core/
│   ├── parsers/
│   ├── post_processors/
│   ├── serialisers/
│   ├── tools/
│   └── models/
└── tests/
    ├── unit/
    └── benchmarks/
```

- `src/config.py` - environment-driven settings object
- `src/core/cache.py` - in-memory + Redis caching layer
- `src/core/router.py` - file format determination
- `src/core/executor.py` - process pool execution with thread limits
- `src/parsers/*` - per-format parsing logic
- `src/post_processors/*` - enrich parse results
- `src/serialisers/*` - Markdown/JSON/text serializer
- `src/tools/*` - tool wrappers for MCP requests

---

## Configuration

### Required packages

- python >= 3.11
- packages listed in `requirements.txt`

### Optional services

- Redis (for shared cache)
- LibreOffice (for `.doc` conversion; installed in Dockerfile)

### Environment variables (`MCP_` prefix)

| Variable | Default | Description |
|---|---|---|
| `MCP_APP_NAME` | `Parsival` | Application name (unused in code currently) |
| `MCP_PROCESS_POOL_SIZE` | `4` | Max worker processes for parsing |
| `MCP_MAX_FILE_SIZE_MB` | `500` | Max file bytes for non-stream parse |
| `MCP_MAX_STREAM_FILE_SIZE_MB` | `2048` | Max file bytes for stream parse |
| `MCP_HYBRID_HASH_THRESHOLD_MB` | `50` | Threshold for full vs partial hash in cache key |
| `MCP_REDIS_ENABLED` | `false` | Enables Redis cache backend |
| `MCP_REDIS_URL` | `None` | URL to Redis server |
| `MCP_REDIS_TTL` | `3600` | Redis key TTL (seconds) |
| `MCP_SENTRY_ENABLED` | `false` | Enable Sentry (not bundled in code path)
| `MCP_SENTRY_DSN` | `None` | Sentry DSN
| `MCP_LIBREOFFICE_PATH` | `None` | Override LibreOffice path
| `MCP_MAX_LIBREOFFICE_WORKERS` | `2` | Max concurrent LibreOffice conversions
| `MCP_SUBPROCESS_TIMEOUT_SEC` | `30` | Subprocess timeout in doc parser
| `MCP_ALLOWED_DIRECTORIES` | `[., /tmp]` | directories permitted for file read paths
| `MCP_WORKSPACE_ROOT` | `.` | root directory boundary for security
| `MCP_TRANSPORT` | `fastmcp` | transport selector: `fastmcp` or `stdio` |

### Non-prefixed env vars from parser

| Variable | Default | Purpose |
|---|---|---|
| `LIBREOFFICE_BINARY` | `soffice` | LibreOffice CLI binary |
| `LIBREOFFICE_TIMEOUT_SEC` | `30` | conversion process timeout |
| `LIBREOFFICE_SECONDARY_KILL_TIMEOUT_SEC` | `5` | wait before kill signal buffer |
| `LIBREOFFICE_MAX_CONCURRENT` | `2` | concurrent conversions |

---

## Local development

### Install

```bash
pip install -r requirements.txt
```

### Run unit tests

```bash
pytest -q
```

### Run stdio smoke test

```bash
python scripts/tool_smoke_test_stdio.py
```

### Run legacy SSE smoke test

```bash
python scripts/tool_smoke_test_http.py
```

### Run benchmarks

```bash
pytest -q tests/benchmarks/test_benchmarks.py
```

### Static checks

```bash
ruff check .
python -m mypy src tests
```

### Add pre-commit

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

---

## Running in Docker

### Build

```bash
docker build -t parsival:latest .
```

### Run

Recommended (stdio mode, no port mapping required):

```bash
docker run --rm -i -e PYTHONUNBUFFERED=1 -e MCP_TRANSPORT=stdio -e PYTHONPATH=/app parsival:latest
```

Legacy rollback (FastMCP SSE/HTTP):

```bash
docker run --rm -p 8000:8000 \
  -e PYTHONUNBUFFERED=1 \
  -e PYTHONPATH=/app \
  -e MCP_TRANSPORT=fastmcp \
  -e FASTMCP_SERVER_HOST=0.0.0.0 \
  -e FASTMCP_SERVER_PORT=8000 \
  parsival:latest
```

### Run with docker compose

Recommended stdio service:

```bash
docker compose up parsival
```

Legacy SSE profile/service:

```bash
docker compose --profile legacy-sse up parsival-legacy-sse
```

### Compose (single host)

```bash
docker compose up --build
```

Container includes LibreOffice and `python-magic` dependencies required for DOC/DOCX and format sniffing.

---

## API and tools

Parsival exposes FastMCP tools. Use your preferred MCP client to call tools by name.

### `read_file`
- `path`: str
- `output_format`: "markdown" | "json" | "text" (default "markdown")
- `page_range`: [start, end] (1-indexed)
- `include_images`: bool (default true)
- `max_tokens_hint`: int
- `stream`: bool (default false)

Returns `ReadFileResult` (status, format, content, metadata, errors, cache_hit, request_id).

### `get_metadata`
- `path`: str
- Returns `DocumentMetadata` object (file_format, page_count, table_count, etc.)

### `extract_table`
- `path`: str
- `table_index`: int
- `sheet_name`: Optional[str]
- Returns `TableResult`

### `extract_images`
- `path`: str
- `page_range`: Optional[tuple[int,int]]
- `max_dimension`: Optional[int]
- Returns list[`ImageRef`]

### `convert_to_markdown`
- `path`: str
- Returns markdown string

### `search_file`
- `path`: str
- `query`: str
- `top_k`: int
- Uses BM25 ranking on section text (via `rank-bm25`)

### `list_supported_formats`
- no params
- returns available `FileFormat` values and server version

---

## Parser details

### Supported file formats

- PDF: `src/parsers/pdf_parser.py` (PyMuPDF + optional pdfplumber tables)
- DOCX: `src/parsers/docx_parser.py` (python-docx)
- DOC: `src/parsers/doc_parser.py` (LibreOffice conversion + DOCX parser)
- XLSX: `src/parsers/xlsx_parser.py` (openpyxl, polars)
- CSV: `src/parsers/csv_parser.py` (polars, utf-8 fallbacks)
- PPTX: `src/parsers/pptx_parser.py` (python-pptx)
- HTML: `src/parsers/html_parser.py` (BeautifulSoup + markdownify)
- TXT/MD: `src/parsers/text_parser.py` (plain text heuristics)

### Parse workflow

- `parse_file` determines format with `FormatRouter.detect`.
- Parser returns `ParseResult`, including `sections`, `tables`, `images`, `metadata`, `errors`.
- `stream=True` dispatches parser `stream_chunks`, bypassing cache prefetch.
- `max_tokens_hint` is a soft truncation applied post-parse.

### Error handling

- Corrupt/encrypted docs return `ParseStatus.FAILED` with `ParseError` code (e.g. `encrypted`, `corrupt`).
- Oversized files return `ParseStatus.OVERSIZE` (source path/size in metadata).
- The parse flow protects against changed file state between read and result flushing.

---

## Cache behavior

- Cache key built in `src/core/cache.py` as `SHA256(file) + ':' + SHA256(opts)`.
- Options considered: output_format, page_range, include_images, max_tokens_hint, max_dimension.
- In-memory LRU cache `cachetools.LRUCache` with size sample based on JSON size of ParseResult.
- Redis backend if `MCP_REDIS_ENABLED=true` and `MCP_REDIS_URL` is set.
- Redis fallback automatically to in-memory on connection failure.
- Use `MCP_REDIS_TTL` (default 3600s).

---

## Testing and CI

### Local test run

```bash
pytest -q
```

### Coverage

```bash
coverage run -m pytest -q
coverage report -m --fail-under=90
```

### CI pipeline is in

- `.github/workflows/ci.yml`
  - tests against Python 3.11/3.12/3.13
  - `ruff check .`
  - coverage + codecov

---

## Troubleshooting

### Path sanitation

`src/core/security.py` enforces `MCP_WORKSPACE_ROOT` and `MCP_ALLOWED_DIRECTORIES`. If you get `SecurityError`:

- set `MCP_WORKSPACE_ROOT` to your repo root
- add permitted directories via `MCP_ALLOWED_DIRECTORIES`

### Unsupported formats

If parsing fails with unsupported format, check extension + file magic and use standard formats only.

### LibreOffice failures

- Ensure `soffice` is installed in PATH (Dockerfile includes `libreoffice-*` packages)
- Increase:
  - `export LIBREOFFICE_TIMEOUT_SEC=60`
  - `export MCP_MAX_LIBREOFFICE_WORKERS=4`

### Redis caching

- If no Redis configured, the service works with in-memory cache.
- Set `MCP_REDIS_ENABLED=true` and `MCP_REDIS_URL=redis://localhost:6379/0`.

---

## Maintainer notes

- This README is generated from code and supported configs in `src/` and `Docs/`.
- For extensions, add parser class in `src/parsers` and register with `@register(FileFormat.X)`.
- To expose a new MCP tool, define in `src/tools` and add a decorated function in `src/app.py`.

