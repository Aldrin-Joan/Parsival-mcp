import re
from typing import List, Dict, Any
from rank_bm25 import BM25Okapi

from src.core.router import FormatRouter
from src.parsers.registry import get_parser
from src.models.tool_responses import SearchHit
from src.models.enums import OutputFormat
from src.core.security import validate_safe_path
from src.core.logging import get_logger

logger = get_logger(__name__)

# In-memory index cache: {path: {mtime: float, bm25: BM25, sections: List}}
_INDEX_CACHE: Dict[str, Any] = {}
_INDEX_LOCK = __import__("threading").Lock()


def _tokenize(text: str) -> List[str]:
    """Tokenizes text for BM25 ranking."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return [t for t in cleaned.split() if t]


async def _get_or_create_index(path: str) -> Dict[str, Any]:
    """Retrieves or builds the BM25 index for a file."""
    from src.app import get_cache

    safe_path = validate_safe_path(path)
    mtime = safe_path.stat().st_mtime

    if path in _INDEX_CACHE and _INDEX_CACHE[path]["mtime"] == mtime:
        return _INDEX_CACHE[path]

    # Build index
    logger.info("search_indexing_start", path=path)
    cache = get_cache()
    opts = {"output_format": OutputFormat.MARKDOWN.value}
    key = cache.make_cache_key(path, opts)
    res = await cache.get(key)

    if not res:
        fmt = FormatRouter().detect(str(safe_path))
        res = await get_parser(fmt).parse(safe_path)
        await cache.set(key, res)

    sections = [s for s in res.sections if s.content]
    docs = [_tokenize(s.content) for s in sections]
    bm25 = BM25Okapi(docs) if docs else None

    with _INDEX_LOCK:
        _INDEX_CACHE[path] = {"mtime": mtime, "sections": sections, "bm25": bm25}
        return _INDEX_CACHE[path]


def _format_search_hits(query_tokens: List[str], sections: List[Any], scores: Any, top_k: int) -> List[SearchHit]:
    """Sorts and formats the top search hits."""
    # Clamp scores to non-negative values and order by score (desc) + section index (asc).
    scored = [(i, max(0.0, float(scores[i]))) for i in range(len(scores))]
    scored.sort(key=lambda item: (-item[1], sections[item[0]].index))

    hits = []
    for i, score in scored[:top_k]:
        sec = sections[i]

        snippet = sec.content[:200]
        offset = sec.content.lower().find(query_tokens[0])
        hits.append(
            SearchHit(section_index=sec.index, page=sec.page, snippet=snippet, score=score, offset=max(0, offset))
        )
    return hits


async def search_file(path: str, query: str, top_k: int = 5) -> List[SearchHit]:
    """
    Performs BM25 semantic search across a document's sections.
    """
    if not query.strip():
        raise ValueError("Empty query")

    try:
        index_data = await _get_or_create_index(path)
    except Exception as exc:
        logger.warning("tool_search_file_index_failed", path=str(path), error=str(exc))
        return []

    bm25, sections = index_data["bm25"], index_data["sections"]

    if not bm25 or not sections:
        return []

    tokens = _tokenize(query)
    if not tokens:
        return []

    scores = bm25.get_scores(tokens)
    return _format_search_hits(tokens, sections, scores, top_k)
