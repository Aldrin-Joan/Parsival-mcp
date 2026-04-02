from types import SimpleNamespace

from src.tools.search_file import _format_search_hits


def test_search_format_hits_keeps_zero_score_hits():
    sections = [
        SimpleNamespace(index=0, page=1, content="first"),
        SimpleNamespace(index=1, page=1, content="second"),
    ]
    scores = [0.0, 0.0]

    hits = _format_search_hits(["x"], sections, scores, top_k=2)

    assert len(hits) == 2
    assert all(hit.score == 0.0 for hit in hits)
    assert [hit.section_index for hit in hits] == [0, 1]


def test_search_format_hits_clamps_negative_scores():
    sections = [
        SimpleNamespace(index=0, page=1, content="a"),
        SimpleNamespace(index=1, page=1, content="b"),
        SimpleNamespace(index=2, page=1, content="c"),
    ]
    scores = [-1.0, 0.2, -0.5]

    hits = _format_search_hits(["x"], sections, scores, top_k=3)

    assert len(hits) == 3
    assert hits[0].score == 0.2
    assert hits[1].score == 0.0
    assert hits[2].score == 0.0


def test_search_format_hits_deterministic_tie_order():
    sections = [
        SimpleNamespace(index=2, page=1, content="a"),
        SimpleNamespace(index=1, page=1, content="b"),
        SimpleNamespace(index=0, page=1, content="c"),
    ]
    scores = [0.5, 0.5, 0.5]

    hits = _format_search_hits(["x"], sections, scores, top_k=3)

    # existing rule is by order by section.index asc for tied top scores
    assert [hit.section_index for hit in hits] == [0, 1, 2]
