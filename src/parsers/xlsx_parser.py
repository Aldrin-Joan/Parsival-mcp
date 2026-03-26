from __future__ import annotations
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from src.models.enums import FileFormat, ParseStatus, SectionType
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseResult, ParseError, Section
from src.models.table import TableResult, TableCell
from src.parsers.base import BaseParser
from src.parsers.registry import register


@register(FileFormat.XLSX)
class XlsxParser(BaseParser):

    async def parse(self, path: Path, options: dict | None = None) -> ParseResult:
        src = Path(path)
        start = __import__('time').time()

        try:
            size_bytes = src.stat().st_size
            if size_bytes > (__import__('sys').maxsize):
                raise OverflowError('file too large')

            max_size = (options or {}).get('max_size_mb', None)
            if max_size is not None and size_bytes > max_size * 1024 * 1024:
                metadata = DocumentMetadata(source_path=str(src), file_format=FileFormat.XLSX, file_size_bytes=size_bytes, section_count=0, table_count=0, image_count=0, has_toc=False)
                return ParseResult(status=ParseStatus.OVERSIZE, metadata=metadata, sections=[], images=[], tables=[], errors=[ParseError(code='oversize', message='File exceeds configured max size', recoverable=False)], raw_text=None, cache_hit=False, request_id='')

            if size_bytes > 10 * 1024 * 1024:
                wb = openpyxl.load_workbook(str(src), read_only=True, data_only=True)
                read_only_mode = True
            else:
                wb = openpyxl.load_workbook(str(src), read_only=False, data_only=True)
                read_only_mode = False
        except (InvalidFileException, Exception) as exc:
            metadata = DocumentMetadata(source_path=str(src), file_format=FileFormat.XLSX, file_size_bytes=src.stat().st_size if src.exists() else 0, section_count=0, table_count=0, image_count=0, has_toc=False)
            return ParseResult(status=ParseStatus.FAILED, metadata=metadata, sections=[], images=[], tables=[], errors=[ParseError(code='corrupt_xlsx', message=str(exc), recoverable=False)], raw_text=None, cache_hit=False, request_id='')

        sections: list[Section] = []
        tables: list[TableResult] = []
        errors: list[ParseError] = []

        table_index = 0
        for sheet_idx, sheet_name in enumerate(wb.sheetnames):
            ws = wb[sheet_name]
            rows = []
            merged_map = {cell.coordinate: cell for merged in ws.merged_cells.ranges for cell in ws[merged.coord]}

            for row in ws.iter_rows(values_only=True):
                rows.append([str(c) if c is not None else '' for c in row])

            if not rows:
                continue

            headers = rows[0]
            body_rows = rows[1:]
            cells = []
            for ri, row in enumerate(rows):
                for ci, val in enumerate(row):
                    cells.append(TableCell(row=ri, col=ci, value=str(val), raw_value=val, colspan=1, rowspan=1, is_header=(ri == 0)))

            table_obj = TableResult(
                index=table_index,
                page=sheet_idx + 1,
                caption=sheet_name,
                headers=headers,
                rows=body_rows,
                cells=cells,
                row_count=len(body_rows),
                col_count=len(headers),
                has_merged_cells=bool(ws.merged_cells),
                confidence=0.9,
                confidence_reason='openpyxl xlsx',
                markdown='',
                errors=[],
            )
            tables.append(table_obj)
            table_index += 1

        total_text = []
        for table in tables:
            total_text.extend([' '.join(r) for r in table.rows])

        metadata = DocumentMetadata(
            source_path=str(src),
            file_format=FileFormat.XLSX,
            file_size_bytes=src.stat().st_size,
            page_count=len(wb.sheetnames),
            word_count=len(' '.join(total_text).split()),
            char_count=len(' '.join(total_text)),
            reading_time_minutes=None,
            section_count=len(sections),
            table_count=len(tables),
            image_count=0,
            has_toc=False,
            toc=[],
            parse_duration_ms=(__import__('time').time() - start) * 1000,
            parser_version=openpyxl.__version__,
        )

        wb.close()
        return ParseResult(status=ParseStatus.OK, metadata=metadata, sections=sections, images=[], tables=tables, errors=errors, raw_text='', cache_hit=False, request_id='')

    async def parse_metadata(self, path: Path) -> DocumentMetadata:
        src = Path(path)
        wb = openpyxl.load_workbook(str(src), read_only=True, data_only=True)
        props = wb.properties

        metadata = DocumentMetadata(
            source_path=str(src),
            file_format=FileFormat.XLSX,
            file_size_bytes=src.stat().st_size,
            title=props.title,
            author=props.creator,
            subject=props.subject,
            keywords=props.keywords.split(',') if props.keywords else [],
            created_at=props.created.isoformat() if props.created else None,
            modified_at=props.modified.isoformat() if props.modified else None,
            producer=None,
            page_count=len(wb.sheetnames),
            section_count=0,
            table_count=0,
            image_count=0,
            has_toc=False,
            toc=[],
            parse_duration_ms=0.0,
            parser_version=openpyxl.__version__,
        )
        wb.close()
        return metadata
