import tempfile
from pathlib import Path
from src.core.router import FormatRouter, UnsupportedFormatError
from src.models.enums import FileFormat


def test_format_router_extension():
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        f.write(b'%PDF-1.4 foo')
        path = f.name
    try:
        fmt = FormatRouter().detect(path)
        assert fmt == FileFormat.PDF
    finally:
        Path(path).unlink(missing_ok=True)


def test_format_router_unknown():
    with tempfile.NamedTemporaryFile(suffix='.unknown', delete=False) as f:
        f.write(b'')
        path = f.name
    try:
        fmt = FormatRouter().detect(path)
        assert fmt == FileFormat.TEXT
    finally:
        Path(path).unlink(missing_ok=True)
