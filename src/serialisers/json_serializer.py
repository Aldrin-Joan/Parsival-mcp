from __future__ import annotations
import json
from typing import Iterator
from src.models.parse_result import ParseResult


class JSONSerializer:
    """Handles JSON serialization and streaming for ParseResults."""

    @staticmethod
    def serialize(result: ParseResult) -> str:
        """Full serialization of the result object."""
        return result.model_dump_json(indent=2, exclude_none=True)

    @staticmethod
    def stream(result: ParseResult) -> Iterator[str]:
        """Streams the ParseResult as a JSON object chunk by chunk."""
        yield "{\n"

        # 1. Metadata
        meta = result.metadata.model_dump(exclude_none=True)
        yield '  "metadata": ' + json.dumps(meta, indent=2) + ",\n"

        # 2. Sections (Array)
        yield '  "sections": [\n'
        for idx, sec in enumerate(result.sections):
            text = json.dumps(sec.model_dump(exclude_none=True), indent=2)
            chunk = "    " + text.replace("\n", "\n    ")
            if idx < len(result.sections) - 1:
                chunk += ","
            yield chunk + "\n"
        yield "  ],\n"

        # 3. Remaining fields
        yield from JSONSerializer._stream_footer(result)
        yield "}"

    @staticmethod
    def _stream_footer(res: ParseResult) -> Iterator[str]:
        """Helper to stream the remaining JSON footer fields."""

        def dump(obj):
            return json.dumps(obj, indent=2)

        fields = {
            "images": [i.model_dump(exclude_none=True) for i in res.images],
            "tables": [t.model_dump(exclude_none=True) for t in res.tables],
            "errors": [e.model_dump(exclude_none=True) for e in res.errors],
            "raw_text": res.raw_text,
            "cache_hit": res.cache_hit,
            "status": res.status,
        }

        items = list(fields.items())
        for idx, (key, val) in enumerate(items):
            suffix = ",\n" if idx < len(items) - 1 else "\n"
            yield f'  "{key}": {dump(val)}{suffix}'
