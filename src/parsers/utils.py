from pathlib import Path
from zipfile import ZipFile, BadZipFile

from src.config import settings


class FileOversizeError(ValueError):
    def __init__(self, message: str, size_mb: float, limit_mb: float, stream_allowed: bool):
        super().__init__(message)
        self.size_mb = size_mb
        self.limit_mb = limit_mb
        self.stream_allowed = stream_allowed


def normalize_text(text: str | bytes | None) -> str:
    """Ensure text is valid UTF-8 with replacement for invalid chars."""
    if text is None:
        return ""

    if isinstance(text, bytes):
        decoded = text.decode("utf-8", errors="replace")
    else:
        decoded = str(text)

    normalized = decoded.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    return normalized


def is_docx_encrypted(path: Path) -> bool:
    """Detect encrypted .docx by checking for encryption-related package parts."""
    if not path.exists() or not path.is_file():
        return False

    try:
        with ZipFile(path, "r") as zf:
            names = [x.lower() for x in zf.namelist()]
    except BadZipFile:
        return False
    except Exception:
        return False

    return any("encryptioninfo" in n or "encryptedpackage" in n or "encryption" in n for n in names)


def enforce_file_size(
    path: Path,
    max_size_mb: int | None = None,
    max_stream_size_mb: int | None = None,
    stream_mode: bool = False,
) -> None:
    """Raise FileOversizeError if file is too large for parse/stream."""
    if not path.exists() or not path.is_file():
        return

    file_size_mb = path.stat().st_size / (1024.0 * 1024.0)

    if max_size_mb is None:
        max_size_mb = settings.MAX_FILE_SIZE_MB
    if max_stream_size_mb is None:
        max_stream_size_mb = settings.MAX_STREAM_FILE_SIZE_MB

    if stream_mode:
        if file_size_mb > max_stream_size_mb:
            raise FileOversizeError(
                f"File too large for streaming ({file_size_mb:.2f} MB > {max_stream_size_mb} MB)",
                file_size_mb,
                max_stream_size_mb,
                stream_allowed=False,
            )
        return

    if file_size_mb <= max_size_mb:
        return

    stream_allowed = file_size_mb <= max_stream_size_mb
    raise FileOversizeError(
        f"File size {file_size_mb:.2f} MB exceeds max allowed parse size {max_size_mb} MB",
        file_size_mb,
        max_size_mb,
        stream_allowed=stream_allowed,
    )
