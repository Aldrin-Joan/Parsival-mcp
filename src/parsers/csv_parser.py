from __future__ import annotations
from pathlib import Path
import csv
import chardet

from src.models.enums import FileFormat, ParseStatus
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseResult, ParseError
from src.models.table import TableResult, TableCell
from src.parsers.base import BaseParser
from src.parsers.registry import register


@register(FileFormat.CSV)
class CsvParser(BaseParser):
    async def parse(self, path: Path, options: dict | None = None) -> ParseResult:
        src = Path(path)
        start = __import__("time").time()

        try:
            raw = src.read_bytes()
        except Exception as exc:
            metadata = DocumentMetadata(
                source_path=str(src),
                file_format=FileFormat.CSV,
                file_size_bytes=src.stat().st_size if src.exists() else 0,
                section_count=0,
                table_count=0,
                image_count=0,
                has_toc=False,
            )
            return ParseResult(
                status=ParseStatus.FAILED,
                metadata=metadata,
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code="file_read_error", message=str(exc), recoverable=False)],
                raw_text=None,
                cache_hit=False,
                request_id="",
            )

        detect = chardet.detect(raw[:4096])
        encoding = detect.get("encoding") or "utf-8"

        try:
            text = raw.decode(encoding, errors="replace")
        except Exception:
            text = raw.decode("utf-8", errors="replace")

        dial = csv.Sniffer().sniff(text.splitlines()[0] if text else ",") if text.strip() else csv.excel
        reader = csv.reader(text.splitlines(), delimiter=dial.delimiter)

        rows = list(reader)
        if not rows:
            table = []
        else:
            headers = rows[0]
            body = rows[1:]
            cells = []
            for ri, row in enumerate(rows):
                for ci, val in enumerate(row):
                    cells.append(
                        TableCell(
                            row=ri, col=ci, value=str(val), raw_value=val, colspan=1, rowspan=1, is_header=(ri == 0)
                        )
                    )

            table = TableResult(
                index=0,
                page=None,
                caption=None,
                headers=headers,
                rows=body,
                cells=cells,
                row_count=len(body),
                col_count=len(headers),
                has_merged_cells=False,
                confidence=0.95,
                confidence_reason="csv parser",
                markdown="",
                errors=[],
            )

        metadata = DocumentMetadata(
            source_path=str(src),
            file_format=FileFormat.CSV,
            file_size_bytes=src.stat().st_size,
            page_count=None,
            word_count=len(text.split()),
            char_count=len(text),
            reading_time_minutes=None,
            section_count=0,
            table_count=1 if rows else 0,
            image_count=0,
            has_toc=False,
            toc=[],
            parse_duration_ms=(__import__("time").time() - start) * 1000,
            parser_version="csv-parser",
        )

        return ParseResult(
            status=ParseStatus.OK,
            metadata=metadata,
            sections=[],
            images=[],
            tables=[table] if rows else [],
            errors=[],
            raw_text=text,
            cache_hit=False,
            request_id="",
        )

    async def parse_metadata(self, path: Path) -> DocumentMetadata:
        src = Path(path)
        raw = src.read_bytes()
        detect = chardet.detect(raw[:4096])
        enc = detect.get("encoding") or "utf-8"
        data = raw.decode(enc, errors="replace")
        line_count = len(data.splitlines())

        return DocumentMetadata(
            source_path=str(src),
            file_format=FileFormat.CSV,
            file_size_bytes=src.stat().st_size,
            page_count=None,
            section_count=0,
            table_count=1 if line_count > 0 else 0,
            image_count=0,
            has_toc=False,
            toc=[],
            parse_duration_ms=0.0,
            parser_version="csv-parser",
        )
