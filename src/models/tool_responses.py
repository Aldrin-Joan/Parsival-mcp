from __future__ import annotations
from pydantic import BaseModel
from .enums import OutputFormat, ParseStatus
from .parse_result import ParseError
from .metadata import DocumentMetadata


class ReadFileResult(BaseModel):
    status: ParseStatus
    format: OutputFormat
    content: str
    metadata: DocumentMetadata
    errors: list[ParseError] = []
    cache_hit: bool = False
    request_id: str


class StreamChunk(BaseModel):
    chunk_index: int
    total_chunks: int | None
    section_type: str
    content: str
    is_final: bool
    request_id: str


class SearchHit(BaseModel):
    section_index: int
    page: int | None
    snippet: str
    score: float
    offset: int
