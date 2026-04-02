# REMAINING_WORK

This document captures all remaining work to bring Parsival to production-grade completion. Each phase addresses a single specific item.

## Phase 1: PyMuPDF / fitz compatibility shim
- Problem: `fitz` import can resolve to incompatible package (`fitz` not PyMuPDF), causing `fitz.open` madness.
- Why necessary: PDF parsing is core functionality; inability to open PDFs breaks the entire project.
- Affected files: `fitz/__init__.py`, `src/parsers/pdf_parser.py`, tests that import `fitz`.
- Root cause: environment has conflicting `fitz` package from non-PyMuPDF distribution.
- Exact implementation:
  - Primary source: `pymupdf` module (as shipped by PyMuPDF) should be used.
  - shim should map `fitz` name to `pymupdf` namespace early (root `fitz` package or module should be used from local path prior to site-packages).
  - If neither is available, raise clear `ImportError`.
- Edge cases/failures:
  - `pymupdf` missing
  - both installed but incompatible package is first on sys.path.
- Concurrency/async: none.
- Performance: none.
- Testing: new unit tests verifying `import fitz` in this repo loads `pymupdf` functions and has `open`/`Rect`.
- Acceptance: `pytest` passes for all PDF parser tests and `fitz.open` sample runs.
- Risk if unresolved: project nonfunctional on any host with non-PyMuPDF `fitz` package.

## Phase 2: `FastMCP` startup hook compatibility and cache initialization
- Problem: `FastMCP` may not provide `on_startup`; currently code uses decorator that can fail.
- Why necessary: parser startup and cache setup must run robustly across versions.
- Affected files: `src/app.py`, `src/core/cache.py`.
- Root cause: API differences between versions of `fastmcp`.
- Implementation:
  - `src/app.py` should detect `mcp.on_startup` and register hook only if available.
  - Always run `await cache_store.initialize()` inside parse call as fallback.
  - `ContentHashStore.initialize` should asynchronously establish Redis if configured.
- Edge cases: repeated startup calls must be idempotent; sacrifies minimal extra latency.
- Concurrency: ensure `initialize` is async and non-blocking.
- Testing: unit test for when `on_startup` missing and parse still works.
- Acceptance: no `AttributeError` in startup path.
- Risk: uninitialized cache leading to runtime failures or missing optional Redis.

## Phase 3: Document server version output in supported formats list
- Problem: `list_supported_formats_tool` expected `server_version`; previous code omitted it.
- Why necessary: existing tests check this and users/clients rely on it.
- Affected: `src/tools/list_supported_formats.py`, `src/__init__.py`.
- Root cause: missing metadata in response.
- Implementation:
  - Set `__version__` in `src/__init__.py` (done).
  - Lookup value in tool and include fallback `'unknown'`.
- Testing: existing test validates field.
- Debt: none.

## Phase 4: Search scoring behavior and deterministic ranking
- Problem: hits were dropped if scores <=0, causing empty results for valid keyword tests.
- Why necessary: search tool must return relevance even when normalized score is zero.
- Affected: `src/tools/search_file.py`, related tests.
- Root cause: overly aggressive negative/zero filtering.
- Implementation:
  - Keep top-k results always, applying `max(0.0, score)` but not filtering-out all zeroes.
  - Consider setting a minimum threshold if needed for noise.
- Edge cases: no sections, empty query, path not allowed, file changes invalidating cache.
- Concurrency: `_INDEX_CACHE` has thread lock.
- Testing: existing search tests should pass.

## Phase 5: PDF parser resource cleanup and parser_version safety
- Problem: doc objects were not guaranteed closed; parser_version attribute may be missing.
- Why necessary: file locks can prevent deletions in Windows, causing test cleanup to fail.
- Affected: `src/parsers/pdf_parser.py`.
- Root cause: missing explicit `doc.close()` in parse and parse_metadata; reliance on `fitz.__version__`.
- Implementation:
  - Add `try/finally` around parsing and ensure `doc.close()` always called.
  - `parser_version` uses `getattr(fitz, '__version__', 'n/a')`.
- Testing: repeated parse/open/close loop, file removal success in tests.

## Phase 6: Project-level docs and completeness record
- Problem: no dedicated remaining-work doc existed.
- Why necessary: required by request, and facilitates hand-off.
- Affected: `REMAINING_WORK.md` in root.
- Implementation: this file provides phase-by-phase scope and acceptance.

## Phase 7: Production hardening polish
- Problem: unfinished production-grade features (audit, monitoring, high volume limits, S3 path support, etc.).
- Why necessary: these are required for reliable, secure deployment at scale.
- Affected: multiple modules (`src/core/*`, `src/tools/*`, `src/parsers/*`).
- Root cause: current implementation focuses on functional feature parity, not ops in production.
- Implementation:
  - Add support for S3/GCS/HTTP input URI via temporary download + cache key set.
  - Add request auditing/logging trees in `src/core/logging.py` (request_id, path_hash).
  - Add rate limiting and tenant partitioning hooks in overall tool layer.
  - Ensure max memory/CPU overcommit detection in `src/core/executor.py`.
- Edge cases: remote provider auth failures, partial file download, streaming cancellations.
- Concurrency: ensure download/parse pipeline is non-blocking and cancellable.
- Testing: e2e integration tests with mocked S3/GCS endpoints.
- Acceptance: flags and docs in place; no unhandled exceptions on remote path input.
- Risk: a production crash unhandled for remote paths.
