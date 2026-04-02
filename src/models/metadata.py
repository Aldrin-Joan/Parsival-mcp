from __future__ import annotations
from pydantic import BaseModel


class TOCEntry(BaseModel):
    level: int
    title: str
    page: int | None
    section_index: int


class DocumentMetadata(BaseModel):
    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: list[str] = []

    source_path: str
    file_format: str
    file_size_bytes: int = 0
    created_at: str | None = None
    modified_at: str | None = None
    producer: str | None = None

    page_count: int | None = None
    word_count: int | None = None
    char_count: int | None = None
    reading_time_minutes: float | None = None
    section_count: int = 0
    table_count: int = 0
    image_count: int = 0
    has_toc: bool = False

    toc: list[TOCEntry] = []

    parse_duration_ms: float | None = None
    parser_version: str | None = None
