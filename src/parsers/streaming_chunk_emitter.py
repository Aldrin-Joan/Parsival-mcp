from __future__ import annotations
import asyncio
from typing import AsyncIterator

from src.models.metadata import DocumentMetadata
from src.models.parse_result import Section
from src.models.tool_responses import StreamChunk


class StreamingChunkEmitter:
    def __init__(
        self,
        section_iterator: AsyncIterator[Section],
        metadata: DocumentMetadata,
        request_id: str = "",
        maxsize: int = 8,
    ):
        self.section_iterator = section_iterator
        self.metadata = metadata
        self.request_id = request_id
        self._queue: asyncio.Queue[StreamChunk | None] = asyncio.Queue(maxsize=maxsize)
        self._producer_task: asyncio.Task[None] | None = None
        self.max_queue_size_observed = 0
        self._done = False

    @property
    def queue(self) -> asyncio.Queue[StreamChunk | None]:
        return self._queue

    async def _producer(self) -> None:
        section_count = 0
        async for section in self.section_iterator:
            chunk = StreamChunk(
                chunk_index=section_count,
                total_chunks=None,
                section_type=section.type.value if hasattr(section.type, "value") else str(section.type),
                content=section.content,
                is_final=False,
                request_id=self.request_id,
            )
            await self._queue.put(chunk)
            section_count += 1
            self.max_queue_size_observed = max(self.max_queue_size_observed, self._queue.qsize())

        summary = f"streamed {section_count} sections"
        final_chunk = StreamChunk(
            chunk_index=section_count,
            total_chunks=section_count,
            section_type="final",
            content=f"metadata={self.metadata.model_dump_json()}\nsummary={summary}",
            is_final=True,
            request_id=self.request_id,
        )
        await self._queue.put(final_chunk)
        self.max_queue_size_observed = max(self.max_queue_size_observed, self._queue.qsize())
        await self._queue.put(None)

    def __aiter__(self) -> "StreamingChunkEmitter":
        if self._producer_task is None:
            self._producer_task = asyncio.create_task(self._producer())
        return self

    async def __anext__(self) -> StreamChunk:
        if self._done:
            raise StopAsyncIteration

        item = await self._queue.get()
        if item is None:
            self._done = True
            if self._producer_task is not None:
                await self._producer_task
            raise StopAsyncIteration

        if item.is_final:
            self._done = True
            # consume final in this yield, then end on next call
            return item

        return item


async def stream_chunks_from_sections(
    section_iterator: AsyncIterator[Section],
    metadata: DocumentMetadata,
    request_id: str = "",
) -> AsyncIterator[StreamChunk]:
    emitter = StreamingChunkEmitter(section_iterator=section_iterator, metadata=metadata, request_id=request_id)
    async for chunk in emitter:
        yield chunk
