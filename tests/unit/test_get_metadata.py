import time
from pathlib import Path

import pytest

from src.core.router import FormatRouter
from src.parsers.registry import get_parser
from src.tools.get_metadata import get_metadata
from src.models.enums import FileFormat


@pytest.mark.asyncio
async def test_get_metadata_text_file(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("Hello world", encoding="utf-8")

    metadata = await get_metadata(str(p))
    assert metadata.file_format == FileFormat.TEXT
    assert metadata.source_path == str(p)
    assert metadata.word_count == 2


@pytest.mark.asyncio
async def test_get_metadata_does_not_run_full_parse(tmp_path, monkeypatch):
    p = tmp_path / "sample.txt"
    p.write_text("Only metadata", encoding="utf-8")

    # ensure parser.parse is NOT called
    fmt = FormatRouter().detect(str(p))
    parser = get_parser(fmt)

    called = {"parse": False}

    orig_parse = parser.parse

    async def fake_parse(path):
        called["parse"] = True
        return await orig_parse(path)

    monkeypatch.setattr(parser, "parse", fake_parse)

    await get_metadata(str(p))
    assert not called["parse"]


@pytest.mark.asyncio
async def test_get_metadata_large_pdf_benchmark(tmp_path, monkeypatch):
    # Use a fake PDF parser to avoid needing a real large PDF file
    fake_pdf_path = tmp_path / "large.pdf"
    fake_pdf_path.write_bytes(b"%PDF-1.4\n%Dummy")

    class FakeParser:
        async def parse_metadata(self, path: Path):
            # Simulate quick metadata; should still be fast
            from src.models.metadata import DocumentMetadata

            return DocumentMetadata(
                source_path=str(path),
                file_format=FileFormat.PDF,
                file_size_bytes=1234567,
                section_count=0,
                table_count=0,
                image_count=0,
                has_toc=False,
                toc=[],
                word_count=0,
                char_count=0,
                parse_duration_ms=0.0,
                parser_version="fake",
            )

    monkeypatch.setattr("src.parsers.registry._REGISTRY", {FileFormat.PDF: FakeParser()})

    start = time.perf_counter()
    metadata = await get_metadata(str(fake_pdf_path))
    end = time.perf_counter()

    assert metadata.file_format == FileFormat.PDF
    assert metadata.source_path == str(fake_pdf_path)
    assert (end - start) * 1000 < 100
