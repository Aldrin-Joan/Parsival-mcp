from src.models.parse_result import ParseResult, Section, ParseStatus
from src.models.metadata import DocumentMetadata
from src.models.enums import SectionType
from src.models.table import TableResult, TableCell
from src.models.image import ImageRef
from src.serialisers.markdown import MarkdownSerializer
from src.post_processors.image_extractor import ImageExtractor
from src.post_processors.table_normaliser import TableNormaliser
from src.post_processors.metadata_enricher import MetadataEnricher
from src.post_processors.pipeline import PostProcessingPipeline


def test_markdown_serializer_basics():
    meta = DocumentMetadata(
        source_path="/tmp/f",
        file_format="pdf",
        file_size_bytes=100,
        page_count=1,
        table_count=0,
        image_count=0,
        section_count=1,
        has_toc=False,
    )
    result = ParseResult(
        status=ParseStatus.OK,
        metadata=meta,
        sections=[Section(index=0, type=SectionType.HEADING, content="Hello", page=1, level=1, metadata={})],
        images=[],
        tables=[],
        errors=[],
        raw_text="Hello",
        cache_hit=False,
        request_id="1",
    )
    out = MarkdownSerializer.serialize(result)
    assert "---" in out
    assert "# Hello" in out


def test_markdown_serializer_front_matter_strict_keys():
    meta = DocumentMetadata(
        title="Document Title",
        author="Author Name",
        source_path="/tmp/f",
        file_format="pdf",
        file_size_bytes=123,
        page_count=2,
        table_count=1,
        image_count=0,
        section_count=1,
        has_toc=False,
    )
    result = ParseResult(
        status=ParseStatus.OK,
        metadata=meta,
        sections=[Section(index=0, type=SectionType.PARAGRAPH, content="Text")],
        images=[],
        tables=[],
        errors=[],
        raw_text="Text",
        cache_hit=False,
        request_id="1",
    )
    out = MarkdownSerializer.serialize(result)
    assert out.startswith("---\n")
    assert 'title: "Document Title"' in out
    assert 'author: "Author Name"' in out
    assert 'source: "/tmp/f"' in out
    assert 'format: "pdf"' in out
    assert "pages: 2" in out
    assert "generated_at:" in out
    assert "source_path" not in out
    assert "file_format" not in out


def test_low_confidence_table_comment():
    table = TableResult(
        index=0,
        page=1,
        headers=["A"],
        rows=[["1"]],
        cells=[],
        row_count=1,
        col_count=1,
        has_merged_cells=False,
        confidence=0.55,
        confidence_reason="low pattern",
        markdown="",
        errors=[],
    )
    result = ParseResult(
        status=ParseStatus.OK,
        metadata=DocumentMetadata(
            source_path="/tmp/f",
            file_format="pdf",
            file_size_bytes=1,
            section_count=1,
            table_count=1,
            image_count=0,
            has_toc=False,
        ),
        sections=[Section(index=0, type=SectionType.TABLE, content="", table=table)],
        images=[],
        tables=[table],
        errors=[],
        raw_text="",
        cache_hit=False,
        request_id="1",
    )
    out = MarkdownSerializer.serialize(result)
    assert "<!-- low-confidence table (score: 0.55) -->" in out


def test_high_confidence_table_no_low_comment():
    table = TableResult(
        index=0,
        page=1,
        headers=["A"],
        rows=[["1"]],
        cells=[],
        row_count=1,
        col_count=1,
        has_merged_cells=False,
        confidence=0.75,
        confidence_reason="high",
        markdown="",
        errors=[],
    )
    result = ParseResult(
        status=ParseStatus.OK,
        metadata=DocumentMetadata(
            source_path="/tmp/f",
            file_format="pdf",
            file_size_bytes=1,
            section_count=1,
            table_count=1,
            image_count=0,
            has_toc=False,
        ),
        sections=[Section(index=0, type=SectionType.TABLE, content="", table=table)],
        images=[],
        tables=[table],
        errors=[],
        raw_text="",
        cache_hit=False,
        request_id="1",
    )
    out = MarkdownSerializer.serialize(result)
    assert "<!-- low-confidence table" not in out


def test_image_extractor_no_change():
    img = ImageRef(
        index=0,
        page=1,
        width_px=10,
        height_px=10,
        format="png",
        size_bytes=1,
        base64_data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAA6fptVAAAAC0lEQVR4nGNk+A8AAZ0B/fHSAxwAAAAASUVORK5CYII=",
        description_hint="hi",
        confidence=0.75,
    )
    result = ParseResult(
        status=ParseStatus.OK,
        metadata=DocumentMetadata(
            source_path="/tmp/f",
            file_format="pdf",
            file_size_bytes=1,
            section_count=0,
            table_count=0,
            image_count=1,
            has_toc=False,
        ),
        sections=[],
        images=[img],
        tables=[],
        errors=[],
        raw_text="",
        cache_hit=False,
        request_id="1",
    )
    out = ImageExtractor.run(result)
    assert out.images[0].description_hint == "hi"


def test_table_normaliser_jagged():
    table = TableResult(
        index=0,
        page=1,
        headers=["A", "B"],
        rows=[["1"], ["2", "3"]],
        cells=[
            TableCell(row=0, col=0, value="1"),
            TableCell(row=1, col=0, value="2"),
            TableCell(row=1, col=1, value="3"),
        ],
        row_count=2,
        col_count=2,
        has_merged_cells=False,
        confidence=1.0,
        confidence_reason="",
        markdown="",
        errors=[],
    )
    result = ParseResult(
        status=ParseStatus.OK,
        metadata=DocumentMetadata(
            source_path="/tmp/f",
            file_format="pdf",
            file_size_bytes=1,
            section_count=0,
            table_count=1,
            image_count=0,
            has_toc=False,
        ),
        sections=[],
        images=[],
        tables=[table],
        errors=[],
        raw_text="",
        cache_hit=False,
        request_id="1",
    )
    out = TableNormaliser.run(result)
    assert out.tables[0].row_count == 2
    assert out.tables[0].col_count == 2


def test_metadata_enricher_toc():
    sections = [
        Section(index=0, type=SectionType.HEADING, content="H1", page=1, level=1, metadata={}),
        Section(index=1, type=SectionType.PARAGRAPH, content="text", page=1, metadata={}),
    ]
    result = ParseResult(
        status=ParseStatus.OK,
        metadata=DocumentMetadata(
            source_path="/tmp/f",
            file_format="pdf",
            file_size_bytes=1,
            section_count=0,
            table_count=0,
            image_count=0,
            has_toc=False,
        ),
        sections=sections,
        images=[],
        tables=[],
        errors=[],
        raw_text="H1 text",
        cache_hit=False,
        request_id="1",
    )
    out = MetadataEnricher.run(result)
    assert out.metadata.word_count > 0
    assert out.metadata.has_toc is True
    assert len(out.metadata.toc) == 1


def test_pipeline_order():
    sections = [Section(index=0, type=SectionType.HEADING, content="H1", page=1, level=1, metadata={})]
    result = ParseResult(
        status=ParseStatus.OK,
        metadata=DocumentMetadata(
            source_path="/tmp/f",
            file_format="pdf",
            file_size_bytes=1,
            section_count=0,
            table_count=0,
            image_count=0,
            has_toc=False,
        ),
        sections=sections,
        images=[],
        tables=[],
        errors=[],
        raw_text="H1",
        cache_hit=False,
        request_id="1",
    )
    out = PostProcessingPipeline.run(result)
    assert out.metadata.has_toc is True
    assert out.metadata.section_count == 1
