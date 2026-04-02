from __future__ import annotations

from datetime import datetime, timezone

from src.models.parse_result import ParseResult
from src.models.table import TableResult
from src.models.enums import SectionType


def escape_pipe(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_gfm_table(table: TableResult) -> str:
    headers = [escape_pipe(h) for h in table.headers] if table.headers else ["" for _ in range(table.col_count)]
    rows = [[escape_pipe(cell) for cell in row] for row in table.rows]

    col_widths = [max(len(h), 3) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(cell))
            else:
                col_widths.append(len(cell))

    alignments = [":---" for _ in col_widths]

    lines = []
    lines.append("| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |")
    lines.append("| " + " | ".join(a.ljust(w) for a, w in zip(alignments, col_widths)) + " |")
    for row in rows:
        padded = [c.ljust(w) for c, w in zip(row, col_widths)]
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


def _yaml_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return f'"{str(value)}"'


class MarkdownSerializer:
    @staticmethod
    def serialize(result: ParseResult) -> str:
        meta = result.metadata

        lines: list[str] = ["---"]

        front_matter = [
            ("title", meta.title),
            ("author", meta.author),
            ("source", getattr(meta, "source_path", None)),
            ("format", getattr(meta, "file_format", None)),
            ("pages", getattr(meta, "page_count", None)),
        ]

        for key, value in front_matter:
            if value is not None:
                lines.append(f"{key}: {_yaml_scalar(value)}")

        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        lines.append(f"generated_at: {_yaml_scalar(generated_at)}")

        lines.append("---")
        lines.append("")

        body_lines: list[str] = []
        for section in result.sections:
            if section.type == SectionType.HEADING:
                level = section.level or 1
                body_lines.append("#" * level + " " + section.content)
            elif section.type == SectionType.PARAGRAPH:
                body_lines.append(section.content)
            elif section.type == SectionType.TABLE and section.table is not None:
                if section.table.confidence < 0.6:
                    body_lines.append(f"<!-- low-confidence table (score: {section.table.confidence:.2f}) -->")
                body_lines.append(to_gfm_table(section.table))
            elif section.type == SectionType.IMAGE and section.images:
                img = section.images[0]
                body_lines.append(f"![{img.description_hint}]({img.data_uri})")
            else:
                body_lines.append(section.content)
            body_lines.append("")

        for err in result.errors:
            body_lines.append(f"<!-- parse_error: {err.code} {err.message} -->")

        output = "\n".join(lines + body_lines).rstrip() + "\n"
        return output
