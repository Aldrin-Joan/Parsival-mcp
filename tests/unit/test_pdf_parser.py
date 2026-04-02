import os
import tempfile
import time
from pathlib import Path
import fitz
from src.parsers.pdf_parser import PDFParser
from src.models.enums import ParseStatus, SectionType

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from PIL import Image
except ImportError:
    Image = None


def make_pdf_file(text: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    doc.save(tmp.name)
    doc.close()
    return tmp.name


import pytest


@pytest.mark.asyncio
async def test_pdf_metadata():
    path = make_pdf_file("Hello World")
    try:
        parser = PDFParser()
        metadata = await parser.parse_metadata(Path(path))
        assert metadata.source_path == path
        assert metadata.file_format == "pdf"
        assert metadata.page_count == 1
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_pdf_parser_text():
    path = make_pdf_file("Hello World")
    try:
        parser = PDFParser()
        result = await parser.parse(Path(path))
        assert result.status == ParseStatus.OK
        assert result.metadata.source_path == path
        assert len(result.sections) >= 1
        assert result.sections[0].type in (SectionType.PARAGRAPH, SectionType.HEADING)
        assert "Hello" in result.raw_text
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_pdf_parser_corrupt_file():
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    with open(tmp.name, "wb") as f:
        f.write(b"%PDF-1.4\n%\x00\x00\x00\ncorrupt content not pdf")

    try:
        parser = PDFParser()
        result = await parser.parse(Path(tmp.name))
        assert result.status == ParseStatus.FAILED
        assert result.errors
        assert result.errors[0].code in ("corrupt", "encrypted")
    finally:
        os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_pdf_parser_encrypted_file():
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    doc = fitz.open()
    doc.new_page()
    doc.save(tmp.name, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    doc.close()

    try:
        parser = PDFParser()
        result = await parser.parse(Path(tmp.name))
        assert result.status == ParseStatus.FAILED
        assert result.errors
        assert result.errors[0].code == "encrypted"
    finally:
        os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_pdf_parser_file_is_closed_after_parse():
    path = make_pdf_file("Hello World")
    try:
        parser = PDFParser()
        for _ in range(3):
            result = await parser.parse(Path(path))
            assert result.status == ParseStatus.OK
        os.unlink(path)
        assert not Path(path).exists()
    finally:
        if Path(path).exists():
            os.unlink(path)


@pytest.mark.asyncio
async def test_pdf_parser_parser_version_fallback(monkeypatch):
    path = make_pdf_file("Hello World")
    original_version = getattr(fitz, "__version__", None)
    if hasattr(fitz, "__version__"):
        delattr(fitz, "__version__")

    try:
        parser = PDFParser()
        metadata = await parser.parse_metadata(Path(path))
        assert metadata.parser_version == "n/a"

        result = await parser.parse(Path(path))
        assert result.status == ParseStatus.OK
        assert result.metadata.parser_version == "n/a"
    finally:
        if original_version is not None:
            setattr(fitz, "__version__", original_version)
        if Path(path).exists():
            os.unlink(path)


@pytest.mark.asyncio
async def test_pdf_parser_image_extraction():
    if Image is None:
        pytest.skip("Pillow required for image creation")

    path = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name
    try:
        # create test image
        img = Image.new("RGB", (10, 10), color="red")
        buf = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(buf.name, format="PNG")
        buf.close()

        doc = fitz.open()
        page = doc.new_page()
        rect = fitz.Rect(72, 72, 72 + 10, 72 + 10)
        page.insert_image(rect, filename=buf.name)
        doc.save(path)
        doc.close()

        parser = PDFParser()
        result = await parser.parse(Path(path))
        assert result.status == ParseStatus.OK
        assert result.metadata.image_count == len(result.images) == 1
        assert result.images[0].page == 1
        assert result.images[0].format.lower() in ("png", "jpeg", "jpg")
    finally:
        os.unlink(path)
        os.unlink(buf.name)


@pytest.mark.asyncio
async def test_pdf_parser_table_extraction(monkeypatch):
    if pdfplumber is None:
        pytest.skip("pdfplumber not installed")

    class DummyPage:
        def extract_tables(self):
            return [[["A", "B"], ["1", "2"]]]

    class DummyPbDoc:
        def __init__(self):
            self.pages = [DummyPage()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(pdfplumber, "open", lambda path: DummyPbDoc())

    path = make_pdf_file("no table parallel")
    try:
        parser = PDFParser()
        result = await parser.parse(Path(path))
        assert result.status == ParseStatus.OK
        assert result.metadata.table_count == 1
        assert len(result.tables) == 1
        table = result.tables[0]
        assert table.row_count == 1
        assert table.col_count == 2
        assert table.headers == ["A", "B"]
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_pdf_stream_sections_honors_paging_and_timing():
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} text")
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    doc.save(tmp.name)
    doc.close()

    try:
        parser = PDFParser()
        assert parser.supports_streaming() is True

        start = time.perf_counter()
        sections = []
        first_emit_time = None
        idx = 0

        async for section in parser.stream_sections(Path(tmp.name), options={"simulate_page_delay": 0.2}):
            if idx == 0:
                first_emit_time = time.perf_counter() - start
            sections.append(section)
            idx += 1

        total_time = time.perf_counter() - start

        assert first_emit_time is not None
        assert first_emit_time < total_time
        assert first_emit_time < 0.3

        page_sequence = [s.page for s in sections]
        assert page_sequence == sorted(page_sequence)
        assert page_sequence[0] == 1
        assert page_sequence[-1] == 3

        assert total_time >= 0.6
    finally:
        os.unlink(tmp.name)
