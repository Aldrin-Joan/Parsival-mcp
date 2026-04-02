from __future__ import annotations
from src.models.parse_result import ParseResult
from src.models.table import TableResult


class TableNormaliser:
    @staticmethod
    def _normalize_row_lengths(table: TableResult) -> TableResult:
        if not table.rows:
            return table

        max_cols = max(len(r) for r in table.rows)
        rows = [list(r) for r in table.rows]
        new_rows = []
        for row in rows:
            if len(row) < max_cols:
                row += [""] * (max_cols - len(row))
            elif len(row) > max_cols:
                row = row[:max_cols]
            new_rows.append(row)

        return table.model_copy(update={"rows": new_rows, "col_count": max_cols, "row_count": len(new_rows)})

    @staticmethod
    def _score_table(table: TableResult) -> float:
        score = table.confidence
        if table.col_count <= 1:
            score -= 0.3
        if any(all(cell == "" for cell in row) for row in table.rows):
            score -= 0.1
        score = max(0.0, min(1.0, score))
        return score

    @classmethod
    def run(cls, result: ParseResult) -> ParseResult:
        tables = []
        for table in result.tables:
            table_norm = cls._normalize_row_lengths(table)
            table_norm = table_norm.model_copy(
                update={
                    "confidence": cls._score_table(table_norm),
                    "confidence_reason": "table normalised",
                }
            )
            tables.append(table_norm)

        return result.model_copy(update={"tables": tables})
