import pytest
from pathlib import Path

from src.parsers.html_parser import HtmlParser
from src.models.enums import FileFormat, ParseStatus, SectionType


@pytest.mark.asyncio
async def test_html_parser_clean_html(tmp_path):
    html = """
    <!DOCTYPE html>
    <html lang=\"en\">
      <head>
        <title>Test Page</title>
        <meta name=\"description\" content=\"A description\">
        <meta name=\"author\" content=\"Author Name\">
      </head>
      <body>
        <h1>Main Title</h1>
        <p>First paragraph.</p>
        <table>
          <tr><th>H1</th><th>H2</th></tr>
          <tr><td>A1</td><td>B1</td></tr>
        </table>
        <img src=\"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/5TZkVIAAAAASUVORK5CYII=\" alt=\"inline\" />
      </body>
    </html>
    """

    f = tmp_path / 'clean.html'
    f.write_text(html, encoding='utf-8')

    parser = HtmlParser()
    result = await parser.parse(f)

    assert result.status == ParseStatus.OK
    assert result.metadata.file_format == FileFormat.HTML
    assert result.metadata.title == 'Test Page'
    assert result.metadata.author == 'Author Name'
    assert result.metadata.table_count == 1
    assert result.metadata.image_count == 1
    assert any(s.type == SectionType.HEADING and 'Main Title' in s.content for s in result.sections)
    assert 'First paragraph.' in result.raw_text


@pytest.mark.asyncio
async def test_html_parser_broken_html(tmp_path):
    html = """
    <html>
      <head><title>Broken
      <meta name=\"description\" content=\"Broken page\">
      <body>
        <p>Text <strong>without close
        <table><tr><td>1</td><td>2</td></tr></table>
      </body>
    </html>
    """
    f = tmp_path / 'broken.html'
    f.write_text(html, encoding='utf-8')

    parser = HtmlParser()
    result = await parser.parse(f)

    assert result.status in (ParseStatus.OK, ParseStatus.PARTIAL)
    assert result.metadata.title == 'Broken'
    assert result.metadata.table_count == 1
    assert 'Text' in result.raw_text


@pytest.mark.asyncio
async def test_html_parser_scripts_styles_removed(tmp_path):
    html = """
    <html><head><title>Script Style</title></head><body>
      <script>var x=1;</script>
      <style>body { color:red; }</style>
      <p>Visible</p>
    </body></html>
    """
    f = tmp_path / 'script_style.html'
    f.write_text(html, encoding='utf-8')

    parser = HtmlParser()
    result = await parser.parse(f)

    assert 'var x' not in result.raw_text
    assert 'body { color' not in result.raw_text
    assert 'Visible' in result.raw_text


@pytest.mark.asyncio
async def test_html_parser_external_and_inline_images(tmp_path):
    html = """
    <html><body>
      <img src=\"http://example.com/image.png\" />
      <img src=\"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/5TZkVIAAAAASUVORK5CYII=\" />
    </body></html>
    """
    f = tmp_path / 'img.html'
    f.write_text(html, encoding='utf-8')

    parser = HtmlParser()
    result = await parser.parse(f)

    assert result.metadata.image_count == 1
    assert len(result.images) == 1
    assert all(img.alt_text is None or img.alt_text == '' for img in result.images)
