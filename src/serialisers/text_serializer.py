from __future__ import annotations
from src.models.parse_result import ParseResult


class TextSerializer:
    """Handles plain text serialization of ParseResult."""

    @staticmethod
    def serialize(result: ParseResult) -> str:
        """Output is a minimal text representation suitable for text-only clients."""
        if result.raw_text:
            return result.raw_text

        lines = []
        for section in result.sections:
            if section.type.name == "HEADING":
                level = section.level or 1
                lines.append("#" * level + " " + section.content)
            else:
                if section.content:
                    lines.append(section.content)

        return "\n\n".join(lines).strip() + "\n" if lines else ""
