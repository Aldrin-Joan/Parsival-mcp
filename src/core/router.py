from __future__ import annotations
from pathlib import Path
from src.models.enums import FileFormat


MIME_TO_FORMAT = {
    "application/pdf": FileFormat.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": FileFormat.DOCX,
    "application/msword": FileFormat.DOC,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": FileFormat.PPTX,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": FileFormat.XLSX,
    "text/csv": FileFormat.CSV,
    "text/html": FileFormat.HTML,
    "text/plain": FileFormat.TEXT,
}

EXTENSION_TO_FORMAT = {
    ".pdf": FileFormat.PDF,
    ".docx": FileFormat.DOCX,
    ".doc": FileFormat.DOC,
    ".pptx": FileFormat.PPTX,
    ".xlsx": FileFormat.XLSX,
    ".csv": FileFormat.CSV,
    ".html": FileFormat.HTML,
    ".htm": FileFormat.HTML,
    ".txt": FileFormat.TEXT,
    ".md": FileFormat.MARKDOWN,
}


class UnsupportedFormatError(Exception):
    pass


class FormatRouter:
    def __init__(self):
        try:
            import magic  # type: ignore
        except ImportError:
            self._magic = None
        else:
            self._magic = magic

    def detect(self, path: str) -> FileFormat:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        mime = None
        if self._magic is not None:
            try:
                mime = self._magic.from_file(str(path), mime=True)
            except Exception:
                mime = None

        if mime and mime in MIME_TO_FORMAT:
            return MIME_TO_FORMAT[mime]

        ext = file_path.suffix.lower()
        ext_fmt = EXTENSION_TO_FORMAT.get(ext)

        try:
            raw = file_path.read_bytes()[:4096]

            if raw.startswith(b"%PDF"):
                return FileFormat.PDF
            if b"<html" in raw.lower():
                return FileFormat.HTML

            # For files with explicit non-text extension, trust the extension first,
            # but allow markdown/csv content override for text-like extensions as needed.
            if ext_fmt and ext_fmt not in (FileFormat.TEXT, FileFormat.MARKDOWN, FileFormat.CSV):
                return ext_fmt

            content_csv = b"," in raw and b"\n" in raw
            content_markdown = raw.strip().startswith(b"#") or b"\n#" in raw

            if content_csv:
                return FileFormat.CSV
            if content_markdown:
                return FileFormat.MARKDOWN

            if ext_fmt:
                return ext_fmt

            if b"\x00" in raw:
                raise UnsupportedFormatError(path)

            # Determine likely text; non-printables (excluding common whitespace) indicate binary
            non_printables = sum(1 for b in raw if b < 0x09 or (0x0A < b < 0x20) or b == 0x7F)
            if raw and (non_printables / len(raw)) > 0.30:
                raise UnsupportedFormatError(path)

            if ext == "":
                return FileFormat.TEXT

            raise UnsupportedFormatError(path)
        except UnsupportedFormatError:
            raise
        except Exception:
            raise UnsupportedFormatError(path)
