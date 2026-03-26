from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncIterator
from pathlib import Path

from src.models.parse_result import ParseResult, Section
from src.models.metadata import DocumentMetadata


class BaseParser(ABC):

    @abstractmethod
    async def parse(self, path: Path, options: dict | None = None) -> ParseResult:
        raise NotImplementedError

    @abstractmethod
    async def parse_metadata(self, path: Path) -> DocumentMetadata:
        raise NotImplementedError

    async def stream_sections(
        self, path: Path, options: dict | None = None
    ) -> AsyncIterator[Section]:
        result = await self.parse(path, options)
        for section in result.sections:
            yield section

    def supports_streaming(self) -> bool:
        return False
