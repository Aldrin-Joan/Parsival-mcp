from pathlib import Path
from typing import Optional

from src.core.router import FormatRouter
from src.parsers.registry import get_parser
from src.models.table import TableResult


def _to_gfm(table: TableResult) -> str:
    if not table.headers:
        return ''

    def escape(cell: str) -> str:
        return cell.replace('|', '\\|')

    header_row = '| ' + ' | '.join(escape(c) for c in table.headers) + ' |'
    separator = '| ' + ' | '.join('---' for _ in table.headers) + ' |'
    body_rows = []
    for row in table.rows:
        body_rows.append('| ' + ' | '.join(escape(str(c)) for c in row) + ' |')

    return '\n'.join([header_row, separator] + body_rows)


async def extract_table(path: str, table_index: int = 1, sheet_name: Optional[str] = None) -> TableResult:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f'File not found: {path}')

    fmt = FormatRouter().detect(path)
    parser = get_parser(fmt)
    result = await parser.parse(source)

    tables = result.tables
    if sheet_name is not None:
        tables = [tbl for tbl in tables if tbl.caption == sheet_name]

    if not tables:
        raise IndexError('No tables found for given filter')

    idx = table_index - 1
    if idx < 0 or idx >= len(tables):
        raise IndexError(f'table_index {table_index} out of range (1..{len(tables)})')

    table = tables[idx]
    table.markdown = _to_gfm(table)
    return table
