# 09 — Future Enhancements

---

## 1. Plugin System for New File Types

### Current State (V1)

Parsers are Python classes registered via `@register(FileFormat.X)` decorator. Adding a new format requires:
1. Adding to the `FileFormat` enum
2. Creating a parser class
3. Adding MIME/extension mappings
4. Importing in `__init__.py`

This is extensible but requires modifying the core package.

### V2: External Plugin System

Allow third-party parsers to be installed as separate Python packages without modifying the core:

```python
# In a third-party package: Parsival-epub
# setup.cfg / pyproject.toml
[options.entry_points]
mcp_file_server.parsers =
    epub = mcp_file_server_epub:EPUBParser
```

Core plugin loader at startup:

```python
# src/parsers/plugin_loader.py
import importlib.metadata

def load_plugins():
    for ep in importlib.metadata.entry_points(group="mcp_file_server.parsers"):
        parser_cls = ep.load()
        fmt_name   = ep.name.upper()
        # Dynamically add to FileFormat enum if not present
        if fmt_name not in FileFormat._value2member_map_:
            FileFormat._value2member_map_[fmt_name] = fmt_name
        _REGISTRY[FileFormat(fmt_name)] = parser_cls()
        logger.info("plugin_loaded", format=fmt_name, plugin=ep.value)
```

**Formats to prioritise as plugins:**
- EPUB (ebooks) — `ebooklib`
- RTF — LibreOffice subprocess
- ODP/ODS/ODT (LibreOffice formats) — LibreOffice subprocess
- HEIC/HEIF images — `pillow-heif`
- Audio transcription hooks — Whisper integration
- ZIP/archive — recurse into contained documents

---

## 2. OCR Support

### Use Case

Scanned PDFs and images (JPG, PNG, TIFF) contain only raster pixels — no extractable text. The current system returns `ImageRef` objects for these pages but no text.

### Design

OCR is implemented as a **post-processor plugin**, not in the parser itself. This keeps parsers simple and makes OCR optional (it's slow and expensive).

```python
# src/post_processors/ocr_processor.py
class OCRProcessor:
    """
    Runs pytesseract on pages detected as image-only (no text extracted by parser).
    Triggered when section.content == "" and section.images is non-empty.
    """

    def __init__(self, engine: str = "tesseract", languages: list[str] = None):
        self.engine    = engine
        self.languages = languages or ["eng"]

    def run(self, result: ParseResult) -> ParseResult:
        new_sections = []
        for section in result.sections:
            if section.type == SectionType.IMAGE and not section.content:
                ocr_text = self._ocr_section(section)
                if ocr_text:
                    new_sections.append(section.model_copy(update={
                        "content": ocr_text,
                        "metadata": {**section.metadata, "ocr": "true", "ocr_engine": self.engine},
                        "confidence": 0.7,  # OCR confidence ceiling
                    }))
                    continue
            new_sections.append(section)
        return result.model_copy(update={"sections": new_sections})

    def _ocr_section(self, section: Section) -> str:
        import pytesseract
        from PIL import Image
        import io, base64
        if not section.images:
            return ""
        img_data = base64.b64decode(section.images[0].base64_data)
        img      = Image.open(io.BytesIO(img_data))
        return pytesseract.image_to_string(img, lang="+".join(self.languages)).strip()
```

**Activation:** `read_file(..., options={"ocr": true})`

**Performance note:** Tesseract is ~500ms–2s per page. For a 50-page scanned PDF this is 25–100 seconds. GPU-accelerated EasyOCR or cloud Vision API should be used for production OCR workloads.

**System dependency:** `tesseract-ocr` + `libtesseract-dev` + language packs.

---

## 3. Vision Model Integration

### Use Case

Instead of (or alongside) OCR, use a vision-capable LLM to:
1. Generate rich `description_hint` for embedded images
2. Extract structured data from chart images (bar charts, pie charts, etc.)
3. Interpret diagram images into Markdown descriptions

### Design

```python
# src/post_processors/vision_enricher.py
class VisionEnricher:
    """
    Calls a vision LLM API to generate descriptions for images.
    Only runs if VISION_API_KEY is configured.
    """

    PROMPT = """Describe this image concisely for use as alt text in a document.
    If the image is a chart or graph, describe the data it contains.
    If it contains text, transcribe the key text.
    Maximum 100 words."""

    async def enrich(self, image_ref: ImageRef) -> ImageRef:
        if not settings.VISION_API_KEY:
            return image_ref

        description = await self._call_vision_api(image_ref.data_uri)
        return image_ref.model_copy(update={
            "description_hint": description,
            "confidence": 0.95,
        })

    async def _call_vision_api(self, data_uri: str) -> str:
        # Pluggable: OpenAI GPT-4V, Anthropic Claude, Google Gemini
        # Implementation depends on VISION_PROVIDER setting
        ...
```

**Activation:** Opt-in via `extract_images(..., vision_descriptions=True)` or server-level config.

**Cost control:** Vision API calls are expensive. Cache vision descriptions separately keyed by image hash, not document hash.

---

## 4. Cloud Deployment

### 4.1 Containerised MCP Server (Current V1)

Docker + Redis. Single tenant. Suitable for team deployment.

### 4.2 Serverless / Edge Deployment (V2+)

**Challenge:** LibreOffice cannot run in serverless (Lambda, Cloud Run) due to binary size (~500MB) and cold start.

**Solution:** Split architecture:
```
FastMCP Server (Cloud Run / ECS)
    │
    ├──► Redis (Elasticache / Upstash)
    │
    └──► LibreOffice Converter Service (separate container, always-warm)
              ← called via HTTP for DOC conversion only
```

LibreOffice Converter Service exposes a single endpoint:
```
POST /convert
Content-Type: application/octet-stream  (raw .doc bytes)
Accept: application/vnd.openxmlformats-...  (returns .docx bytes)
```

This separates the heavy binary from the main server and enables independent scaling.

### 4.3 S3 / GCS File Reference Support

Currently `path` is a local filesystem path. Add support for cloud storage URIs:

```python
# In FormatRouter, before format detection:
if path.startswith("s3://"):
    local_path = await download_s3(path, to=tmpdir)
elif path.startswith("gs://"):
    local_path = await download_gcs(path, to=tmpdir)
else:
    local_path = Path(path)
```

**Cache key for remote files:** SHA-256 of the downloaded bytes (not the URL, which is not content-stable).

### 4.4 Multi-Tenant SaaS

For a hosted SaaS version:
- Per-tenant cache namespacing in Redis: `tenant:{id}:mcp-fs:{hash}`
- Per-tenant file size limits
- Per-tenant rate limiting (token bucket per `client_id` from MCP metadata)
- Audit log: `{tenant_id, path_hash, format, duration_ms, cache_hit}` (no file content)

---

## 5. API Exposure Beyond MCP

### 5.1 REST API Layer

Expose the same parsing functionality via a standard HTTP REST API for non-MCP clients:

```
POST /v1/parse
Content-Type: multipart/form-data
  file: <binary>
  output_format: markdown | json
  include_images: true | false

Response: ReadFileResult (JSON)
```

Implementation: FastAPI mounted alongside FastMCP. Both share the same parser registry, cache, and post-processors.

### 5.2 gRPC API

For high-throughput programmatic use (e.g. document ingestion pipelines):

```protobuf
service FileParser {
  rpc ParseFile (ParseRequest) returns (ParseResult);
  rpc ParseFileStream (ParseRequest) returns (stream StreamChunk);
  rpc GetMetadata (MetadataRequest) returns (DocumentMetadata);
}
```

Protocol Buffers provide ~40% smaller payload than JSON for binary image data.

### 5.3 Webhook / Async Processing

For very large files that exceed reasonable synchronous latency:

```
POST /v1/parse/async
Response: { "job_id": "uuid", "status_url": "/v1/jobs/uuid" }

GET /v1/jobs/{job_id}
Response: { "status": "pending|processing|done|failed", "result_url": "..." }

GET /v1/jobs/{job_id}/result
Response: ReadFileResult
```

---

## 6. Semantic Search and RAG Integration

Beyond BM25 keyword search (`search_file` tool), add vector embedding search:

```python
# Tool: embed_file
# Creates per-section embeddings stored in a vector store
# Enables semantic similarity search across parsed documents

async def embed_file(path: str, embedding_model: str = "text-embedding-3-small") -> EmbedResult:
    result   = await parse_file(path)
    sections = [s.content for s in result.sections if s.content]
    vectors  = await embedding_client.embed_batch(sections)
    vector_store.upsert(doc_id=result.metadata.source_path, vectors=vectors, texts=sections)
    return EmbedResult(doc_id=..., section_count=len(sections))
```

This turns the MCP server into a lightweight RAG document store. Pairs well with pgvector (PostgreSQL) or Qdrant.

---

## 7. Incremental / Delta Parsing

For documents that change frequently (e.g. a live report), avoid re-parsing unchanged sections:

1. Parse full document on first request → cache sections with per-section hash
2. On subsequent requests: compare section hashes to cached values
3. Only re-parse sections whose hash changed
4. Return merged result (cached unchanged sections + fresh changed sections)

**Challenge:** Section boundaries in PDFs are not stable across minor edits (page reflow can change section indices). More tractable for structured formats (XLSX cell deltas, DOCX paragraph deltas).

---

## 8. Table-to-DataFrame Shortcut

For XLSX/CSV heavy workloads, add a tool that returns a table directly as a Polars DataFrame-compatible Arrow IPC stream:

```python
# Tool: extract_dataframe
# Returns: base64-encoded Arrow IPC bytes
# Client-side: polars.read_ipc(io.BytesIO(base64.b64decode(result.ipc_bytes)))
```

This eliminates the CSV round-trip and is the fastest possible path for numerical data.

---

## 9. Batch Processing Tool

For agents that need to process many files in a single call:

```python
# Tool: batch_read_files
# Input: paths: list[str], output_format: OutputFormat
# Output: list[ReadFileResult]
# Internally: asyncio.gather(*[read_file(p) for p in paths], return_exceptions=True)
```

Rate-limited to `MAX_BATCH_SIZE=20` to prevent runaway resource usage.

---

## 10. Format Conversion Tool

Expose document conversion as a first-class tool, not just an internal implementation detail:

```python
# Tool: convert_file
# Input:  path: str, target_format: "pdf" | "docx" | "pptx" | "html"
# Output: ConvertResult { output_path: str, size_bytes: int, duration_ms: float }
```

Backed by LibreOffice for office formats, Pandoc for text formats. Returns a local path that can then be read via `read_file`.
