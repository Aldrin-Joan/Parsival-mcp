import tempfile
from pathlib import Path
from src.core.router import FormatRouter
from src.models.enums import FileFormat


def test_format_router_extension():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 foo")
        path = f.name
    try:
        fmt = FormatRouter().detect(path)
        assert fmt == FileFormat.PDF
    finally:
        Path(path).unlink(missing_ok=True)


def test_format_router_unknown():
    with tempfile.NamedTemporaryFile(suffix=".unknown", delete=False) as f:
        f.write(b"")
        path = f.name
    try:
        try:
            FormatRouter().detect(path)
            assert False, "Expected UnsupportedFormatError"
        except Exception as exc:
            from src.core.router import UnsupportedFormatError

            assert isinstance(exc, UnsupportedFormatError)
    finally:
        Path(path).unlink(missing_ok=True)


def test_format_router_no_extension_text():
    with tempfile.NamedTemporaryFile(suffix="", delete=False) as f:
        f.write(b"Hello world\nThis is plain text\n")
        path = f.name
    try:
        fmt = FormatRouter().detect(path)
        assert fmt == FileFormat.TEXT
    finally:
        Path(path).unlink(missing_ok=True)


def test_format_router_binary_no_extension():
    with tempfile.NamedTemporaryFile(suffix="", delete=False) as f:
        f.write(b"\x00\x01\x02\x03")
        path = f.name
    try:
        from src.core.router import UnsupportedFormatError

        try:
            FormatRouter().detect(path)
            assert False, "Expected UnsupportedFormatError"
        except UnsupportedFormatError:
            pass
    finally:
        Path(path).unlink(missing_ok=True)
