from src.models.table import TableCell, TableResult


def test_table_models():
    cell = TableCell(row=0, col=0, value="A", raw_value=1, colspan=1, rowspan=1)
    assert cell.value == "A"

    table = TableResult(
        index=0,
        headers=["c1"],
        rows=[["1"]],
        cells=[cell],
        row_count=1,
        col_count=1,
    )
    assert table.row_count == 1
    assert table.rows[0][0] == "1"
