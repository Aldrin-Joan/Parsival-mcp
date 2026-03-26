from __future__ import annotations
import json
from typing import Iterator

from src.models.parse_result import ParseResult, Section


class JSONSerializer:
    @staticmethod
    def serialize(parse_result: ParseResult) -> str:
        return parse_result.model_dump_json(indent=2, exclude_none=True)

    @staticmethod
    def stream(parse_result: ParseResult) -> Iterator[str]:
        # Metadata first
        metadata = parse_result.metadata.model_dump(exclude_none=True)
        yield '{\n'
        yield '  "metadata": ' + json.dumps(metadata, indent=2) + ',\n'
        yield '  "sections": [\n'

        for idx, section in enumerate(parse_result.sections):
            section_json = json.dumps(section.model_dump(exclude_none=True), indent=2)
            # indent nested section
            chunk = '    ' + section_json.replace('\n', '\n    ')
            if idx < len(parse_result.sections) - 1:
                chunk += ','
            chunk += '\n'
            yield chunk

        yield '  ],\n'

        # Add remaining properties with proper JSON layout
        images_json = json.dumps([img.model_dump(exclude_none=True) for img in parse_result.images], indent=2)
        tables_json = json.dumps([tbl.model_dump(exclude_none=True) for tbl in parse_result.tables], indent=2)
        errors_json = json.dumps([err.model_dump(exclude_none=True) for err in parse_result.errors], indent=2)

        yield '  "images": ' + images_json + ',\n'
        yield '  "tables": ' + tables_json + ',\n'
        yield '  "errors": ' + errors_json + ',\n'
        yield '  "raw_text": ' + json.dumps(parse_result.raw_text) + ',\n'
        yield '  "cache_hit": ' + json.dumps(parse_result.cache_hit) + ',\n'
        yield '  "request_id": ' + json.dumps(parse_result.request_id) + ',\n'
        yield '  "status": ' + json.dumps(parse_result.status) + '\n'
        yield '}'
