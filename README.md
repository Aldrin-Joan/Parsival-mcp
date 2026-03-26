# Parsival

Parsival is a FastMCP-based file parsing service that supports parsing of text, PDF, DOCX, DOC, HTML, CSV, XLSX, PPTX and streaming extraction. It provides safety protections for corrupt and encrypted files, file-size limits, Redis caching, subprocess hardening, and process pool-constrained parallelism.

## Contents
- [Setup](#setup)
- [Usage](#usage)
- [Streaming usage](#streaming-usage)
- [Architecture summary](#architecture-summary)
- [Troubleshooting](#troubleshooting)

## Setup

### Local install

1. Clone repo:
   ```bash
   git clone <repo-url>
   cd Parsival
   ```

2. Create python env:
   ```bash
   python -m venv .venv
   source .venv/bin/activate    # macOS/Linux
   .venv\Scripts\activate     # Windows
   ```

3. Install dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Config (optional): in environment:
   ```bash
   export MCP_REDIS_ENABLED=1
   export MCP_REDIS_URL=redis://localhost:6379/0
   ```

### Docker (recommended)

1. Build image:
   ```bash
   docker build -t parsival:phase5 .
   ```

2. Run container:
   ```bash
   docker run --rm -p 8000:8000 parsival:phase5
   ```

3. Or compose:
   ```bash
   docker compose up --build
   ```

## Usage

### FastMCP host
Run server (via Docker CMD or local):
```bash
python -m fastmcp --host 0.0.0.0 --port 8000 parsival
```

### API actions (pseudo-CLI / endpoint)
- Parse file (non-stream):
  - path -> format auto-detect -> parse with parser
  - `ParseResult` object returns sections/images/tables metadata
- Tools are registered in `src/tools` for file lookup, conversion, metadata.

### Example: parse a local file using direct app function
```python
from src.app import parse_file
from src.models.enums import OutputFormat

result = await parse_file('example.pdf', output_format=OutputFormat.JSON, stream=False)
print(result.status, result.metadata)
```

### Caching
- Redis optional by `MCP_REDIS_ENABLED=true` and `MCP_REDIS_URL`.
- If Redis unavailable, fallback to local LRU in-memory cache.
- TTL controlled by `MCP_REDIS_TTL` (seconds).

## Streaming usage

- Parser stream option in `app.parse_file(path, stream=True)` uses `stream_chunks`.
- In streaming mode, `cache` is skipped and early stream-first outcomes are delivered.
- `PDFParser.stream_sections` emits per-section chunks, with flow control (page delay param for testing).

## Architecture summary

- `src/app.py` is entry point, uses:
  - `FormatRouter` (detects MIME/extension)
  - `registry` (parser lookup)
  - `ContentHashStore` (cache layer with Redis fallback)
  - `PostProcessingPipeline` (metadata normalisation and post-processing)
  - `core.executor.run_parse_in_pool` for CPU-constrained parallel jobs

- Parsers (in `src/parsers`) each implement:
  - `parse(path, options)`
  - `parse_metadata(path)`
  - `stream_sections` (optional)

- Robustness enhancements:
  - Corrupt/encrypted detection
  - UTF-8 normalization
  - file-size enforcement (`MAX_FILE_SIZE_MB`, `MAX_STREAM_FILE_SIZE_MB`)
  - subprocess safety for LibreOffice conversions
  - process pool / thread tuning

- Benchmarking bundle in `tests/benchmarks`.
- CI pipeline in `.github/workflows/ci.yml` runs tests, coverage (>=90%), lint.

## Troubleshooting

### Common issues
- `module 'src.parsers' not found`
  - set PYTHONPATH: `export PYTHONPATH=$(pwd)/src` (or Windows `set PYTHONPATH=%CD%\src`).

- `project.dependencies must be array` on pip install
  - Use `requirements.txt` route (or fix `pyproject.toml` to valid array). This repo currently works by explicit package list due pyproject validation issue.

- `LibreOffice conversion timed out`:
  - Increase `MCP_LIBREOFFICE_TIMEOUT_SEC` or `LIBREOFFICE_TIMEOUT_SEC`.
  - Check `libreoffice` is installed in environment.

- `max size exceeded`:
  - Config `MCP_MAX_FILE_SIZE_MB` / `MCP_MAX_STREAM_FILE_SIZE_MB` in environment.

### Debug logging
- Check `src/core/logging.py` for structured logs.

### Running tests
```bash
pytest -q
pytest -q tests/benchmarks/test_benchmarks.py
```

## Contact
If you have questions or feature requests, open an issue or PR with details.
