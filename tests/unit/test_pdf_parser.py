import os
import tempfile
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
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    tmp.close()
    doc.save(tmp.name)
    doc.close()
    return tmp.name


import pytest

@pytest.mark.asyncio
async def test_pdf_metadata():
    path = make_pdf_file('Hello World')
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
    path = make_pdf_file('Hello World')
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
async def test_pdf_parser_image_extraction():
    if Image is None:
        pytest.skip("Pillow required for image creation")

    path = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False).name
    try:
        # create test image
        img = Image.new('RGB', (10, 10), color='red')
        buf = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        img.save(buf.name, format='PNG')
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
            return [[['A', 'B'], ['1', '2']]]

    class DummyPbDoc:
        def __init__(self):
            self.pages = [DummyPage()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(pdfplumber, 'open', lambda path: DummyPbDoc())

    path = make_pdf_file('no table parallel')
    try:
        parser = PDFParser()
        result = await parser.parse(Path(path))
        assert result.status == ParseStatus.OK
        assert result.metadata.table_count == 1
        assert len(result.tables) == 1
        table = result.tables[0]
        assert table.row_count == 1
        assert table.col_count == 2
        assert table.headers == ['A', 'B']
    finally:
        os.unlink(path)

