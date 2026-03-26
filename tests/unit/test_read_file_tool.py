import os
import tempfile
from pathlib import Path
import docx
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
