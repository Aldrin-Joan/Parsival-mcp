from __future__ import annotations
from pydantic import BaseModel


class TableCell(BaseModel):
    row: int
    col: int
    value: str
    raw_value: str | int | float | bool | None = None
    colspan: int = 1
    rowspan: int = 1
    is_header: bool = False
    alignment: str | None = None


class TableResult(BaseModel):
    index: int
    page: int | None = None
    caption: str | None = None
    headers: list[str] = []
    rows: list[list[str]] = []
    cells: list[TableCell] = []
    row_count: int = 0
    col_count: int = 0
    has_merged_cells: bool = False
    confidence: float = 1.0
    confidence_reason: str = ""
    markdown: str = ""
    errors: list[str] = []
