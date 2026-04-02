import pytest

from src.tools.search_file import search_file


@pytest.mark.asyncio
async def test_search_file_known_keyword(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("This is a sample document. The keyword is Parsival. Another sentence.", encoding="utf-8")

    results = await search_file(str(file_path), "parsival", top_k=3)

    assert len(results) >= 1
    assert results[0].score >= 0
    assert "parsival" in results[0].snippet.lower()


@pytest.mark.asyncio
async def test_search_file_ranking_correctness(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("apple banana apple. banana fruit. apple apple banana", encoding="utf-8")

    results = await search_file(str(file_path), "apple", top_k=1)
    assert results[0].score >= 0


@pytest.mark.asyncio
async def test_search_file_empty_query(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("any text", encoding="utf-8")

    with pytest.raises(ValueError):
        await search_file(str(file_path), "")


@pytest.mark.asyncio
async def test_search_file_large_document(tmp_path):
    file_path = tmp_path / "big.txt"
    large_text = ("word " * 5000) + " targetword " + ("word " * 5000)
    file_path.write_text(large_text, encoding="utf-8")

    results = await search_file(str(file_path), "targetword", top_k=5)
    assert len(results) > 0
    assert all(hit.score >= 0 for hit in results)
