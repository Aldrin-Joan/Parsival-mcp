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
        if ext in EXTENSION_TO_FORMAT:
            return EXTENSION_TO_FORMAT[ext]

        try:
            text = file_path.read_bytes()[:1024]
            if text.startswith(b"%PDF"):
                return FileFormat.PDF
            if b"<html" in text.lower():
                return FileFormat.HTML
            if b"," in text and b"\n" in text:
                return FileFormat.CSV
            if text.strip().startswith(b"#") or b"\n#" in text:
                return FileFormat.MARKDOWN
            return FileFormat.TEXT
        except Exception:
            raise UnsupportedFormatError(path)
