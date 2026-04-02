import importlib
import sys
import tempfile

import pytest


def test_fitz_shim_exports_pymupdf_symbols():
    import fitz

    assert hasattr(fitz, "open"), "fitz shim must expose open()"
    assert hasattr(fitz, "Rect"), "fitz shim must expose Rect"


def test_pdf_parser_uses_fitz_shim():
    from src.parsers.pdf_parser import PDFParser

    parser = PDFParser()

    # create a tiny pdf with pymupdf (through fitz)
    import fitz as f

    doc = f.open()
    page = doc.new_page()
    page.insert_text((72, 72), "hello")
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    path = tmp.name
    doc.save(path)
    doc.close()

    try:
        import asyncio
        from pathlib import Path

        result = asyncio.run(parser.parse(Path(path)))
        assert result.status.name == "OK"
        assert result.metadata.file_format == "pdf"
    finally:
        try:
            import os

            os.unlink(path)
        except Exception:
            pass


def test_fitz_shim_errors_when_pymupdf_missing(monkeypatch):
    importlib.invalidate_caches()

    original_import = importlib.import_module

    def fake_import(name, package=None):
        if name == "pymupdf":
            raise ModuleNotFoundError("No module named pymupdf")
        return original_import(name, package=package)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    sys.modules.pop("fitz", None)

    with pytest.raises(ImportError, match="Could not import PyMuPDF"):
        __import__("fitz")

    # restore module state
    sys.modules.pop("fitz", None)
    monkeypatch.setattr(importlib, "import_module", original_import)
