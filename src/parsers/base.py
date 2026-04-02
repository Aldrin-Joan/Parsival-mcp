from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncIterator
from pathlib import Path

from src.models.parse_result import ParseResult, Section
from src.models.metadata import DocumentMetadata
from src.models.tool_responses import StreamChunk
from src.parsers.streaming_chunk_emitter import stream_chunks_from_sections


class BaseParser(ABC):
    @abstractmethod
    async def parse(self, path: Path, options: dict | None = None) -> ParseResult:
        raise NotImplementedError

    @abstractmethod
    async def parse_metadata(self, path: Path) -> DocumentMetadata:
        raise NotImplementedError

    async def stream_sections(self, path: Path, options: dict | None = None) -> AsyncIterator[Section]:
        result = await self.parse(path, options)
        for section in result.sections:
            yield section

    async def stream_chunks(self, path: Path, options: dict | None = None) -> AsyncIterator["StreamChunk"]:
        metadata = DocumentMetadata(
            source_path=str(path),
            file_format="unknown",
            file_size_bytes=0,
            page_count=None,
            section_count=0,
            table_count=0,
            image_count=0,
            has_toc=False,
        )
        try:
            metadata = await self.parse_metadata(path)
        except Exception:
            pass

        async for chunk in stream_chunks_from_sections(
            self.stream_sections(path, options), metadata, request_id=(options or {}).get("request_id", "")
        ):
            yield chunk

    def supports_streaming(self) -> bool:
        return False
