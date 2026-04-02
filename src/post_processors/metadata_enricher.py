from __future__ import annotations
from src.models.parse_result import ParseResult, SectionType


class MetadataEnricher:
    @staticmethod
    def run(result: ParseResult) -> ParseResult:
        section_count = len(result.sections)
        heading_count = sum(1 for s in result.sections if s.type == SectionType.HEADING)
        table_count = len(result.tables)
        image_count = len(result.images)

        words = sum(len(s.content.split()) for s in result.sections)
        chars = sum(len(s.content) for s in result.sections)

        toc = [
            {"level": s.level or 1, "title": s.content, "page": s.page, "section_index": s.index}
            for s in result.sections
            if s.type == SectionType.HEADING
        ]

        metadata = result.metadata.model_copy(
            update={
                "word_count": words,
                "char_count": chars,
                "reading_time_minutes": words / 200.0 if words else 0.0,
                "section_count": section_count,
                "table_count": table_count,
                "image_count": image_count,
                "has_toc": heading_count >= 1,
                "toc": toc,
            }
        )

        return result.model_copy(update={"metadata": metadata})
