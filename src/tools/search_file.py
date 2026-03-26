import re
from pathlib import Path
from typing import List, Optional

from rank_bm25 import BM25Okapi

from src.core.router import FormatRouter
from src.parsers.registry import get_parser
from src.models.tool_responses import SearchHit
from src.models.enums import OutputFormat

_INDEX_CACHE = {}


def _tokenize(text: str) -> List[str]:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return [token for token in cleaned.split() if token]


async def search_file(path: str, query: str, top_k: int = 5):
    if not query or not query.strip():
        raise ValueError('Query must not be empty')

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f'File not found: {path}')

    from src.app import get_cache

    fmt = FormatRouter().detect(path)
    parser = get_parser(fmt)

    cache = get_cache()
    options = {'output_format': OutputFormat.MARKDOWN.value, 'stream': False}
    cache_key = cache.make_cache_key(path, options)
    cached_result = await cache.get(cache_key)

    if cached_result:
        parse_result = cached_result
    else:
        parse_result = await parser.parse(source)
        # Store result in cache for future calls
        await cache.set(cache_key, parse_result)

    cache_entry = _INDEX_CACHE.get(path)
    file_mtime = source.stat().st_mtime

    if cache_entry is None or cache_entry['mtime'] != file_mtime:
        sections = [s for s in parse_result.sections if s.content]
        documents = [_tokenize(s.content) for s in sections]
        bm25 = BM25Okapi(documents) if documents else None
        _INDEX_CACHE[path] = {
            'mtime': file_mtime,
            'sections': sections,
            'bm25': bm25,
            'documents': documents,
        }
    else:
        sections = cache_entry['sections']
        bm25 = cache_entry['bm25']

    if bm25 is None or not sections:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        raise ValueError('Query tokenization produced empty tokens')

    scores = bm25.get_scores(query_tokens)
    top_indexes = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    results: List[SearchHit] = []
    for i in top_indexes:
        section = sections[i]
        snippet = section.content[:200]
        offset = section.content.lower().find(query_tokens[0])
        score_val = float(scores[i])
        # Normalize to non-negative for user-facing relevance
        score_val = max(0.0, score_val)
        results.append(SearchHit(section_index=section.index, page=section.page, snippet=snippet, score=score_val, offset=offset if offset >= 0 else 0))

    return results
