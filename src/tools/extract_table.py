from typing import Optional
from src.core.router import FormatRouter
from src.parsers.registry import get_parser
from src.models.table import TableResult
from src.core.security import validate_safe_path
from src.core.logging import get_logger

logger = get_logger(__name__)


def _to_gfm(table: TableResult) -> str:
    """Converts a TableResult to GitHub Flavored Markdown."""
    if not table.headers:
        return ""

    def escape(cell: str) -> str:
        return str(cell).replace("|", "\\|").replace("\n", "<br>")

    header = "| " + " | ".join(escape(c) for c in table.headers) + " |"
    separator = "| " + " | ".join("---" for _ in table.headers) + " |"
    rows = ["| " + " | ".join(escape(c) for c in r) + " |" for r in table.rows]

    return "\n".join([header, separator] + rows)


async def extract_table(path: str, table_index: int = 1, sheet_name: Optional[str] = None) -> TableResult:
    """
    Extracts a specific table from a file.

    Args:
        path: Validated path to the file.
        table_index: 1-based index of the table to extract.
        sheet_name: Optional filter for spreadsheet sheet names.

    Returns:
        TableResult with markdown representation.
    """
    safe_path = validate_safe_path(path)
    logger.info("tool_extract_table_start", path=str(safe_path), index=table_index)

    fmt = FormatRouter().detect(str(safe_path))
    parser = get_parser(fmt)
    result = await parser.parse(safe_path)

    tables = result.tables
    if sheet_name is not None:
        tables = [tbl for tbl in tables if tbl.caption == sheet_name]

    if not tables:
        logger.warning("tool_extract_table_none", path=str(safe_path))
        raise IndexError("No tables found for given filter")

    idx = table_index - 1
    if idx < 0 or idx >= len(tables):
        raise IndexError(f"table_index {table_index} out of range (1..{len(tables)})")

    table = tables[idx]
    table.markdown = _to_gfm(table)

    logger.info("tool_extract_table_complete", path=str(safe_path), rows=table.row_count)
    return table
