from __future__ import annotations
from pydantic import BaseModel
from .metadata import DocumentMetadata
from .table import TableResult
from .image import ImageRef
from .enums import SectionType, ParseStatus


class ParseError(BaseModel):
    code: str
    message: str
    page: int | None = None
    offset: int | None = None
    recoverable: bool = False


class Section(BaseModel):
    index: int
    type: SectionType
    content: str = ""
    page: int | None = None
    level: int | None = None
    language: str | None = None
    table: TableResult | None = None
    images: list[ImageRef] = []
    notes: str | None = None
    confidence: float = 1.0
    metadata: dict[str, str] = {}


class ParseResult(BaseModel):
    status: ParseStatus
    metadata: DocumentMetadata
    sections: list[Section] = []
    images: list[ImageRef] = []
    tables: list[TableResult] = []
    errors: list[ParseError] = []
    raw_text: str | None = None
    cache_hit: bool = False
    request_id: str
