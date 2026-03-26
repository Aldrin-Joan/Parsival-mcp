# 08 — Edge Cases

This document specifies **exact handling** for every known failure mode. "Handle errors properly" is not acceptable — each scenario specifies the detection method, the recovery action, and the exact `ParseResult` shape returned.

---

## 1. File Corruption

### 1.1 Truncated Files

**Detection:** The parser library raises an exception before completing (e.g. `fitz.FileDataError: cannot open broken document`).

**Handling:**
```python
try:
    doc = fitz.open(path)
except fitz.FileDataError as e:
    return ParseResult(
        status=ParseStatus.FAILED,
        metadata=DocumentMetadata(source_path=str(path), file_format=fmt, ...),
        sections=[],
        errors=[ParseError(code="corrupt", message=str(e), recoverable=False)],
    )
```

**For partially readable files** (e.g. PDF where pages 1–10 parse and pages 11+ are corrupt):

```python
errors = []
sections = []
for page_num in range(doc.page_count):
    try:
        page = doc.load_page(page_num)
        sections.extend(parse_page(page))
    except Exception as e:
        errors.append(ParseError(
            code="page_render_failed",
            message=f"Page {page_num+1}: {str(e)}",
            page=page_num+1,
            recoverable=True,
        ))

status = ParseStatus.OK if not errors else ParseStatus.PARTIAL
```

### 1.2 Corrupt DOCX (Invalid ZIP)

DOCX files are ZIP archives. If the ZIP is corrupt:
```python
try:
    doc = docx.Document(path)
except BadZipFile as e:
    return _failed_result(path, fmt, code="corrupt_zip", message=str(e))
```

### 1.3 Corrupt XLSX

```python
try:
    wb = load_workbook(path, data_only=True)
except Exception as e:
    # openpyxl raises generic Exception for corrupt files
    return _failed_result(path, fmt, code="corrupt_xlsx", message=str(e))
```

---

## 2. Unsupported Formats

**Detection:** `FormatRouter.detect()` returns `FileFormat.UNKNOWN` or raises `UnsupportedFormatError`.

**Handling:**
```python
try:
    fmt = FormatRouter().detect(path)
    parser = get_parser(fmt)
except UnsupportedFormatError as e:
    return ReadFileResult(
        status=ParseStatus.UNSUPPORTED,
        format=output_format,
        content="",
        metadata=DocumentMetadata(source_path=path, file_format=FileFormat.UNKNOWN, ...),
        errors=[ParseError(code="unsupported_format", message=str(e), recoverable=False)],
    )
```

The response is still a valid `ReadFileResult` with `status=UNSUPPORTED`. Agents check `status` before using `content`.

---

## 3. Oversized Files

**Detection:** Check file size before any parsing.

```python
MAX_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024

size = Path(path).stat().st_size
if size > MAX_BYTES:
    return ReadFileResult(
        status=ParseStatus.OVERSIZE,
        content="",
        metadata=DocumentMetadata(
            source_path=path,
            file_size_bytes=size,
            ...
        ),
        errors=[ParseError(
            code="oversize",
            message=f"File is {size/1e6:.1f}MB; limit is {settings.MAX_FILE_SIZE_MB}MB",
            recoverable=False,
        )],
    )
```

**Note:** The check happens before the content-hash computation so even the mmap hash is skipped.

---

## 4. Broken / Malformed Tables

### 4.1 PDF Tables with Jagged Rows

pdfplumber's `extract_tables()` may return rows with inconsistent column counts.

**Handling:**
```python
def normalise_rows(raw_rows: list[list]) -> list[list[str]]:
    if not raw_rows:
        return []
    # Determine target column count = mode of row lengths
    from statistics import mode
    target_cols = mode(len(r) for r in raw_rows)
    normalised  = []
    for row in raw_rows:
        if len(row) < target_cols:
            # Pad with empty strings
            row = row + [""] * (target_cols - len(row))
        elif len(row) > target_cols:
            # Truncate extra cells (log warning)
            logger.warning("table_row_truncated", original=len(row), target=target_cols)
            row = row[:target_cols]
        normalised.append([str(c) if c is not None else "" for c in row])
    return normalised
```

Confidence penalty applied: `-0.2` for row count inconsistency.

### 4.2 Single-Column "Tables"

A 1-column table is almost certainly a misidentification (e.g. a list detected as a table).

**Handling:** Apply `-0.3` confidence penalty. Include in output but flag:
```python
if table.col_count == 1:
    table.confidence -= 0.3
    table.confidence_reason += " | single-column: likely misidentified"
```

### 4.3 Empty Tables

Table detected but all cells are empty strings.

```python
all_empty = all(cell == "" for row in table.rows for cell in row)
if all_empty:
    # Do not include in output; log at DEBUG level
    logger.debug("empty_table_skipped", page=page)
    return None
```

### 4.4 Merged Cells in XLSX (read_only mode)

When using `read_only=True` for large XLSX files, merged cell information is unavailable.

**Handling:**
- Set `table.has_merged_cells = False` (unknown, not confirmed false)
- Add `ParseError(code="merged_cells_unavailable", message="...", recoverable=True)`
- Apply `-0.1` confidence penalty

---

## 5. Missing / Unextractable Images

### 5.1 PDF External Image References

Some PDFs reference images via external URLs rather than embedding them.

**Handling:**
```python
if img_ref.startswith("http"):
    image_ref = ImageRef(
        index=idx,
        page=page_num,
        base64_data="",
        data_uri="",
        description_hint=f"External image: {img_ref}",
        confidence=0.0,
        format="unknown",
        size_bytes=0,
    )
```

In Markdown output, this renders as a placeholder: `![External image: https://...]()`

### 5.2 Corrupted Image Data

```python
try:
    img_bytes = doc.extract_image(xref)["image"]
    pil_img   = Image.open(BytesIO(img_bytes))
    pil_img.verify()  # Detect corrupt JPEG/PNG headers
except (UnidentifiedImageError, Exception) as e:
    errors.append(ParseError(
        code="image_corrupt",
        message=f"Image xref={xref}: {str(e)}",
        page=page_num,
        recoverable=True,
    ))
    continue  # Skip this image
```

### 5.3 Zero-Byte Images

```python
if len(img_bytes) == 0:
    errors.append(ParseError(code="image_empty", message=f"xref={xref}", recoverable=True))
    continue
```

### 5.4 Unsupported Image Format (e.g. WMF, EMF in DOCX)

Windows Metafile images in DOCX are not raster images and cannot be base64-encoded as-is.

**Handling:**
```python
if img_format in ("wmf", "emf"):
    image_ref = ImageRef(
        ...,
        base64_data="",
        description_hint=f"Vector image ({img_format}) — conversion not supported",
        confidence=0.0,
    )
```

Future: pipe through LibreOffice to convert to PNG.

---

## 6. Encoding Issues

### 6.1 Unknown File Encoding (CSV, TXT, HTML)

```python
raw = Path(path).read_bytes()
detection = chardet.detect(raw[:4096])
encoding  = detection["encoding"]
confidence = detection["confidence"]

if encoding is None or confidence < 0.5:
    # Cascade: try UTF-8, then Latin-1
    for enc in ("utf-8", "latin-1"):
        try:
            text = raw.decode(enc, errors="strict")
            break
        except UnicodeDecodeError:
            continue
    else:
        # All failed — decode with replace
        text = raw.decode("utf-8", errors="replace")
        errors.append(ParseError(
            code="encoding_fallback",
            message="Could not determine encoding; replacement characters may appear",
            recoverable=True,
        ))
else:
    text = raw.decode(encoding, errors="replace")
```

### 6.2 Null Bytes in Text

Some text files (especially Windows-generated) contain embedded null bytes.

```python
text = text.replace("\x00", "")  # Strip null bytes silently
```

### 6.3 DOCX with Corrupted Character Runs

Some DOCX files have runs with invalid Unicode in their XML.

```python
# In XML parsing
try:
    text = run.text
except Exception:
    text = ""  # Skip malformed run
    errors.append(ParseError(code="run_parse_error", recoverable=True))
```

---

## 7. Race Conditions

### 7.1 File Modified During Parse

A file could be written while being hashed/parsed.

**Detection:** Compare `mtime` before and after parse.

```python
mtime_before = Path(path).stat().st_mtime
result = await parser.parse(path, options)
mtime_after  = Path(path).stat().st_mtime

if mtime_after != mtime_before:
    result.errors.append(ParseError(
        code="file_modified_during_parse",
        message="File mtime changed during parsing; result may be inconsistent",
        recoverable=True,
    ))
    result.status = ParseStatus.PARTIAL
    # Invalidate any cached result for this key
    await cache.invalidate(cache_key)
```

### 7.2 Cache Write Race (Multi-Worker)

Two workers hash the same file simultaneously and both get a cache miss. Both parse and both try to write to cache.

**For in-memory LRU:** Protected by `threading.Lock` — last writer wins. This is safe: both results should be identical for the same file.

**For Redis:** Use `SET ... NX EX ttl` (set if not exists) to avoid unnecessary re-serialisation:

```python
await self._client.set(
    self._prefix + key,
    msgpack.packb(value.model_dump()),
    ex=self._ttl,
    nx=True,   # Only set if not already present
)
```

### 7.3 LibreOffice Temp File Collision

Two concurrent DOC parse requests write to the same output directory.

**Prevention:** Use `tempfile.mkdtemp()` per request, not a shared directory:

```python
async def convert_doc_to_docx(path: Path) -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        outdir = Path(tmpdir)
        # LibreOffice writes to tmpdir; tmpdir is per-request unique
        ...
        docx_path = outdir / (path.stem + ".docx")
        # Copy result out before tmpdir is deleted
        dest = settings.CONVERSION_CACHE_DIR / f"{uuid4()}.docx"
        shutil.copy(docx_path, dest)
    return dest
```

---

## 8. Subprocess Failures (LibreOffice)

### 8.1 LibreOffice Not Installed

**Detection at startup:**

```python
import shutil

@mcp.on_startup
async def startup():
    if not shutil.which("soffice"):
        if settings.DOC_SUPPORT_REQUIRED:
            raise RuntimeError("LibreOffice not found; DOC support unavailable")
        else:
            logger.warning("libreoffice_not_found", formats_disabled=["doc"])
            _REGISTRY.pop(FileFormat.DOC, None)  # Remove DOC parser
```

### 8.2 LibreOffice Crash During Conversion

```python
if proc.returncode not in (0, None):
    stderr_text = stderr.decode(errors="replace")
    raise SubprocessError(
        f"soffice exited with code {proc.returncode}: {stderr_text[:500]}"
    )
```

On `SubprocessError`, the DOC parser returns:
```python
ParseResult(
    status=ParseStatus.FAILED,
    errors=[ParseError(code="subprocess_failed", message=..., recoverable=False)],
)
```

### 8.3 LibreOffice Timeout

```python
try:
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
except asyncio.TimeoutError:
    proc.kill()
    await proc.wait()
    # Retry once
    if attempt == 0:
        return await convert_doc_to_docx(path, attempt=1)
    raise SubprocessError(f"LibreOffice timed out after {TIMEOUT}s (2 attempts)")
```

### 8.4 LibreOffice Output File Missing

Even with returncode 0, the output file may not exist (rare, but happens with corrupt input DOC):

```python
expected_output = outdir / (path.stem + ".docx")
if not expected_output.exists():
    raise SubprocessError(
        f"LibreOffice returned 0 but output not found: {expected_output}"
    )
```

---

## 9. File Not Found / Permission Denied

```python
try:
    size = Path(path).stat().st_size
except FileNotFoundError:
    return _failed_result(path, code="file_not_found",
                          message=f"No such file: {path}")
except PermissionError:
    return _failed_result(path, code="permission_denied",
                          message=f"Cannot read: {path}")
```

---

## 10. Password-Protected Files

### PDF

```python
doc = fitz.open(path)
if doc.is_encrypted:
    # Attempt empty password (common for "view-only" PDFs)
    if not doc.authenticate(""):
        return _failed_result(path, code="encrypted",
                              message="PDF is password-protected")
    # Empty password worked — continue
```

### XLSX

openpyxl raises `InvalidFileException` for password-protected XLSX files. Treat as `encrypted` error.

---

## 11. Extremely Long Single Cells (Tables)

A cell value with 100,000 characters breaks GFM rendering.

```python
MAX_CELL_LEN = 1000

def truncate_cell(value: str) -> str:
    if len(value) <= MAX_CELL_LEN:
        return value
    return value[:MAX_CELL_LEN] + f"… [truncated {len(value)-MAX_CELL_LEN} chars]"
```

---

## 12. Deeply Nested DOCX Tables

DOCX supports tables inside table cells (nested tables).

**Handling:** Flatten nested tables — render each nested table as a separate `TableResult` with a `metadata["nested_in_table"]` flag. Do not attempt to represent nesting in GFM (GFM does not support nested tables).

```python
def extract_table(tbl_element, depth=0) -> list[TableResult]:
    tables = [_parse_table(tbl_element, depth)]
    for cell in _iter_cells(tbl_element):
        for nested_tbl in cell.element.findall(qn("w:tbl")):
            tables.extend(extract_table(nested_tbl, depth+1))
    return tables
```

---

## 13. Zero-Page / Empty Documents

PDF with 0 pages, empty DOCX, empty XLSX:

```python
if doc.page_count == 0:
    return ParseResult(
        status=ParseStatus.OK,  # Not an error — just empty
        sections=[],
        metadata=DocumentMetadata(page_count=0, word_count=0, ...),
        errors=[],
    )
```

In Markdown output: returns only the YAML front-matter block.
