# 03 — Data Contracts

All types are Pydantic v2 models. JSON Schema is auto-generated from these models by FastMCP and exposed to MCP clients.

---

## 1. Core Enums

```python
class FileFormat(str, Enum):
    PDF      = "pdf"
    DOCX     = "docx"
    DOC      = "doc"
    PPTX     = "pptx"
    XLSX     = "xlsx"
    CSV      = "csv"
    HTML     = "html"
    MARKDOWN = "markdown"
    TEXT     = "text"
    UNKNOWN  = "unknown"

class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON     = "json"
    TEXT     = "text"

class ParseStatus(str, Enum):
    OK          = "ok"           # Fully parsed, no errors
    PARTIAL     = "partial"      # Parsed with recoverable errors
    FAILED      = "failed"       # Could not parse
    UNSUPPORTED = "unsupported"  # Format not in registry
    OVERSIZE    = "oversize"     # File exceeds MAX_FILE_SIZE

class SectionType(str, Enum):
    HEADING   = "heading"
    PARAGRAPH = "paragraph"
    TABLE     = "table"
    IMAGE     = "image"
    CODE      = "code"
    LIST      = "list"
    METADATA  = "metadata"
    PAGE_BREAK = "page_break"
    FOOTNOTE  = "footnote"
    CAPTION   = "caption"
```

---

## 2. Metadata Schema

```python
class TOCEntry(BaseModel):
    level:   int           # 1 = h1, 2 = h2 ...
    title:   str
    page:    int | None    # None for formats without page concept
    section_index: int     # Index into ParseResult.sections[]

class DocumentMetadata(BaseModel):
    # Identity
    title:       str | None
    author:      str | None
    subject:     str | None
    keywords:    list[str]

    # Provenance
    source_path: str
    file_format: FileFormat
    file_size_bytes: int
    created_at:  str | None   # ISO 8601
    modified_at: str | None   # ISO 8601
    producer:    str | None   # e.g. "Microsoft Word 16.0"

    # Structure
    page_count:  int | None
    word_count:  int | None
    char_count:  int | None
    reading_time_minutes: float | None   # word_count / 200
    section_count: int
    table_count:  int
    image_count:  int
    has_toc:      bool

    # TOC
    toc: list[TOCEntry]

    # Processing
    parse_duration_ms: float
    parser_version:    str
```

---

## 3. Image Schema

```python
class ImageRef(BaseModel):
    index:            int           # 0-based, document order
    page:             int | None    # Source page (1-based), None if N/A
    width_px:         int | None
    height_px:        int | None
    format:           str           # "png" | "jpeg" | "gif" | "webp" | "svg"
    size_bytes:       int
    base64_data:      str           # Base64-encoded image bytes (no data URI prefix)
    data_uri:         str           # Full data URI: "data:image/png;base64,..."
    description_hint: str           # Caption, alt text, or nearest heading text
    confidence:       float         # 0.0–1.0 confidence that hint is accurate
    alt_text:         str | None    # Original alt text if present in source

    @computed_field
    @property
    def data_uri(self) -> str:
        return f"data:image/{self.format};base64,{self.base64_data}"
```

### Image Representation Strategy

1. **Base64 inline** (default): All images are base64-encoded and embedded in the output. This keeps the response self-contained — no file references that break when files move.
2. **Resize before encoding**: Images wider or taller than `IMAGE_MAX_DIMENSION` (default 2048px) are downscaled preserving aspect ratio using Pillow `LANCZOS` resampling.
3. **EXIF stripping**: Pillow strips EXIF metadata to reduce size and avoid privacy leaks.
4. **Format normalisation**: BMP, TIFF → PNG. Keep JPEG if already JPEG and quality is acceptable. SVG is preserved as-is (no rasterisation unless explicitly requested).
5. **Description hint inference** (in priority order):
   - Explicit alt text or caption in source document
   - Figure/table caption in adjacent paragraph
   - Text extracted from image via pytesseract (if OCR plugin enabled)
   - Nearest heading text
   - `"Image {index+1}"`

---

## 4. Table Schema

```python
class TableCell(BaseModel):
    row:          int
    col:          int
    value:        str                    # Always stringified
    raw_value:    str | int | float | bool | None  # Original typed value
    colspan:      int = 1
    rowspan:      int = 1
    is_header:    bool = False
    alignment:    str | None             # "left" | "center" | "right" | None

class TableResult(BaseModel):
    index:        int                    # 0-based table index in document
    page:         int | None
    caption:      str | None
    headers:      list[str]              # First-row header strings (empty if none)
    rows:         list[list[str]]        # All data rows as string grids
    cells:        list[TableCell]        # Full cell metadata including spans
    row_count:    int
    col_count:    int
    has_merged_cells: bool
    confidence:   float                  # 0.0–1.0
    confidence_reason: str               # Human-readable reason for confidence score
    markdown:     str                    # GFM table string
    errors:       list[ParseError]
```

### Confidence Scoring for Tables

| Condition | Score Adjustment |
|-----------|-----------------|
| Detected by explicit border lines | +0.3 |
| Header row identified via style/formatting | +0.2 |
| Column count consistent across all rows | +0.2 |
| Bounding-box gaps confirm column structure | +0.2 |
| No merged cells | +0.1 |
| Detected by whitespace heuristic only | −0.4 |
| Row count mismatch between methods | −0.3 |
| Contains empty cells (>20% of grid) | −0.1 |
| Single-column table (likely misdetection) | −0.3 |

Final score is clamped to [0.0, 1.0]. Tables with score < 0.5 are flagged as `low_confidence`.

### Merged Cell Handling

Merged cells are flattened in `rows` (the merged value appears in the top-left cell; other spanned positions get empty string). Full span information is preserved in `cells[]` via `rowspan`/`colspan` fields.

---

## 5. Section Schema

```python
class Section(BaseModel):
    index:        int
    type:         SectionType
    content:      str                    # Text content (Markdown fragment)
    page:         int | None
    level:        int | None             # For headings: 1–6
    language:     str | None             # For code blocks: "python", "js", etc.
    table:        TableResult | None     # Populated for type=TABLE
    images:       list[ImageRef]         # Populated for type=IMAGE (usually 1 item)
    notes:        str | None             # Speaker notes (PPTX), footnotes, etc.
    confidence:   float = 1.0
    metadata:     dict[str, str]         # Format-specific extra fields
```

---

## 6. Error Schema

```python
class ParseError(BaseModel):
    code:    str      # e.g. "render_failed", "corrupt_page", "encoding_error"
    message: str
    page:    int | None
    offset:  int | None   # Byte offset in file, if applicable
    recoverable: bool     # True = partial data still returned
```

---

## 7. Top-Level ParseResult

```python
class ParseResult(BaseModel):
    status:    ParseStatus
    metadata:  DocumentMetadata
    sections:  list[Section]
    images:    list[ImageRef]            # All images, deduplicated and ordered
    tables:    list[TableResult]         # All tables, deduplicated and ordered
    errors:    list[ParseError]
    raw_text:  str | None                # Plain text fallback (no structure)
    cache_hit: bool
    request_id: str                      # UUID for tracing
```

---

## 8. Tool Response Schemas

### ReadFileResult

```python
class ReadFileResult(BaseModel):
    status:    ParseStatus
    format:    OutputFormat
    content:   str           # Markdown string, JSON string, or plain text
    metadata:  DocumentMetadata
    errors:    list[ParseError]
    cache_hit: bool
    request_id: str
```

### StreamChunk

```python
class StreamChunk(BaseModel):
    chunk_index:   int
    total_chunks:  int | None
    section_type:  SectionType
    content:       str
    is_final:      bool
    request_id:    str
```

### SearchHit

```python
class SearchHit(BaseModel):
    section_index: int
    page:          int | None
    snippet:       str           # 200-char context window around match
    score:         float         # BM25 score
    offset:        int           # Character offset within section
```

---

## 9. Markdown Output Specification

All `MarkdownSerializer` output must comply with this strict specification.

### 9.1 Document Structure

```markdown
---
title: "Document Title"
author: "Author Name"
source: "/path/to/file.pdf"
format: "pdf"
pages: 42
generated_at: "2025-01-15T10:30:00Z"
---

# Section Heading

Paragraph text...

## Sub-heading

| Col A | Col B | Col C |
|:------|:-----:|------:|
| left  | center| right |

![Figure 1: Chart description](data:image/png;base64,iVBOR...)

> **Note:** Low-confidence content is annotated inline.

```python
def example():
    pass
```

<!-- parse_error: page 12 render failed (recoverable) -->
```

### 9.2 Rules

| Rule | Detail |
|------|--------|
| Headings | ATX style only (`#`). Never Setext (`===` underlines). |
| Tables | GFM pipe tables. Always include alignment row. Escape `\|` in cell values. |
| Images | Data URI embedded. Always include description_hint as alt text. |
| Code | Fenced blocks with language identifier when known. |
| Front-matter | YAML fenced block at document start. Omit null fields. |
| Low-confidence tables | Wrapped in HTML comment `<!-- low-confidence table (score: 0.42) -->` |
| Errors | Appended as HTML comments. Never interrupt content flow. |
| Line endings | LF only (`\n`). No CRLF. |
| Trailing newline | Document ends with exactly one `\n`. |
| Blank lines | Exactly one blank line between sections. Two blank lines before H1/H2. |
| Lists | Use `-` for unordered. Use `1.` for ordered (let renderer handle numbering). |
| Horizontal rules | `---` on its own line. Used only for explicit `<hr>` in source. |
| Footnotes | `[^1]` style at end of document. |
| Internal links | `[text](#anchor)` for TOC entries. Anchor = heading slugified. |

### 9.3 GFM Table Generation

```python
def to_gfm_table(table: TableResult) -> str:
    # 1. Escape pipe characters in all cells
    def escape(s: str) -> str:
        return s.replace("|", "\\|").replace("\n", " ")

    headers = [escape(h) for h in (table.headers or [""] * table.col_count)]
    rows    = [[escape(c) for c in row] for row in table.rows]

    # 2. Compute column widths for alignment
    col_widths = [max(len(h), 3) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    # 3. Alignment from first row cell formatting
    alignments = []
    for col in range(table.col_count):
        cell = next((c for c in table.cells if c.col == col and c.row == 0), None)
        align = cell.alignment if cell else None
        if align == "center":
            alignments.append(":---:")
        elif align == "right":
            alignments.append("---:")
        else:
            alignments.append(":---")

    # 4. Build output
    lines = []
    lines.append("| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |")
    lines.append("| " + " | ".join(a.ljust(w) for a, w in zip(alignments, col_widths)) + " |")
    for row in rows:
        padded = [c.ljust(w) for c, w in zip(row, col_widths)]
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)
```

---

## 10. JSON Schema (ParseResult)

Full JSON Schema generated from the Pydantic models above. Key shape:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ParseResult",
  "type": "object",
  "required": ["status", "metadata", "sections", "images", "tables", "errors"],
  "properties": {
    "status":   { "type": "string", "enum": ["ok", "partial", "failed", "unsupported", "oversize"] },
    "metadata": { "$ref": "#/$defs/DocumentMetadata" },
    "sections": { "type": "array", "items": { "$ref": "#/$defs/Section" } },
    "images":   { "type": "array", "items": { "$ref": "#/$defs/ImageRef" } },
    "tables":   { "type": "array", "items": { "$ref": "#/$defs/TableResult" } },
    "errors":   { "type": "array", "items": { "$ref": "#/$defs/ParseError" } },
    "raw_text": { "type": ["string", "null"] },
    "cache_hit": { "type": "boolean" },
    "request_id": { "type": "string", "format": "uuid" }
  }
}
```

Full `$defs` for all referenced models follow the same pattern as the Pydantic definitions above. Generate via `ParseResult.model_json_schema()`.
