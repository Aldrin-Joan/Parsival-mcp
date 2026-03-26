from src.models.metadata import DocumentMetadata, TOCEntry


def test_metadata_roundtrip():
    toc = [TOCEntry(level=1, title="Intro", page=1, section_index=0)]
    meta = DocumentMetadata(
        title="Test",
        author="Author",
        keywords=["one", "two"],
        source_path="/tmp/f",
        file_format="pdf",
        file_size_bytes=100,
        page_count=1,
        section_count=1,
        toc=toc,
    )
    copy = DocumentMetadata.model_validate(meta.model_dump())
    assert copy.title == "Test"
    assert copy.toc[0].title == "Intro"
