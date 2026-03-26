import os
import tempfile
from pathlib import Path
import docx
import fitz
from src.tools.read_file import _read_file
from src.models.enums import OutputFormat


def make_docx_file():
    f = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
    f.close()
    document = docx.Document()
    document.add_heading('Hello', level=1)
    document.add_paragraph('World')
    document.save(f.name)
    return f.name


import pytest

@pytest.mark.asyncio
async def test_read_file_tool_docx():
    path = make_docx_file()
    try:
        result = await _read_file(path, output_format=OutputFormat.MARKDOWN, stream=False)
        assert result.status.name == 'OK'
        assert '# Hello' in result.content
        assert 'World' in result.content
    finally:
        os.unlink(path)

@pytest.mark.asyncio
async def test_read_file_tool_csv():
    path = tempfile.NamedTemporaryFile(suffix='.csv', delete=False)
    path.write(b'A,B\n1,2\n')
    path.close()
    try:
        result = await _read_file(path.name, output_format=OutputFormat.JSON, stream=False)
        assert result.status.name == 'OK'
        assert '"A"' in result.content
    finally:
        os.unlink(path.name)


@pytest.mark.asyncio
async def test_read_file_tool_streaming_pdf():
    import time
    from src.tools.read_file import _read_file
    from src.parsers.pdf_parser import PDFParser

    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i+1} text")
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    tmp.close()
    doc.save(tmp.name)
    doc.close()

    try:
        # Ensure parser supports streaming path.
        assert PDFParser().supports_streaming() is True

        start = time.perf_counter()
        first_emit = None
        total_chunks = 0
        final_chunk = None

        stream = await _read_file(tmp.name, output_format=OutputFormat.JSON, stream=True)
        assert hasattr(stream, '__aiter__')

        async for chunk in stream:
            if total_chunks == 0:
                first_emit = time.perf_counter() - start
            total_chunks += 1
            if chunk.is_final:
                final_chunk = chunk

        assert total_chunks > 1
        assert first_emit is not None
        assert first_emit < time.perf_counter() - start
        assert final_chunk is not None
        assert final_chunk.is_final
        assert 'metadata' in final_chunk.content

    finally:
        os.unlink(tmp.name)
