from __future__ import annotations
import asyncio
import os
import shutil
import signal
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

from src.models.enums import FileFormat, ParseStatus
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseResult, ParseError
from src.parsers.base import BaseParser
from src.parsers.docx_parser import DocxParser
from src.parsers.registry import register

LIBREOFFICE_BINARY = os.environ.get('LIBREOFFICE_BINARY', 'soffice')
LIBREOFFICE_TIMEOUT_SEC = int(os.environ.get('LIBREOFFICE_TIMEOUT_SEC', '30'))
LIBREOFFICE_SECONDARY_KILL_TIMEOUT_SEC = int(os.environ.get('LIBREOFFICE_SECONDARY_KILL_TIMEOUT_SEC', '5'))
LIBREOFFICE_MAX_CONCURRENT = int(os.environ.get('LIBREOFFICE_MAX_CONCURRENT', '2'))

libreoffice_semaphore = asyncio.Semaphore(LIBREOFFICE_MAX_CONCURRENT)


async def _force_kill(process: asyncio.subprocess.Process) -> None:
    try:
        if process.returncode is None:
            process.kill()
            if os.name == 'posix':
                try:
                    os.kill(process.pid, signal.SIGKILL)
                except Exception:
                    pass
    except ProcessLookupError:
        pass


@register(FileFormat.DOC)
class DocParser(BaseParser):

    async def _convert_doc_to_docx(self, doc_path: Path) -> Tuple[Path, Path]:
        temp_dir = Path(tempfile.mkdtemp(prefix='parsival_docx_'))
        output_path = temp_dir / f'{doc_path.stem}.docx'

        cmd = [
            LIBREOFFICE_BINARY,
            '--headless',
            '--invisible',
            '--nologo',
            '--nodefault',
            '--nofirststartwizard',
            '--nocrashreport',
            '--convert-to',
            'docx',
            '--outdir',
            str(temp_dir),
            str(doc_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            await asyncio.wait_for(process.wait(), timeout=LIBREOFFICE_TIMEOUT_SEC)
        except asyncio.TimeoutError as exc:
            await _force_kill(process)
            try:
                await asyncio.wait_for(process.wait(), timeout=LIBREOFFICE_SECONDARY_KILL_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                await _force_kill(process)
                await process.wait()
            raise TimeoutError('LibreOffice conversion timed out') from exc

        if process.returncode != 0:
            stdout, stderr = await process.communicate()
            raise RuntimeError(
                f'LibreOffice conversion failed (returncode={process.returncode}) stdout={stdout.decode(errors="ignore")} stderr={stderr.decode(errors="ignore")} '
            )

        if not output_path.exists():
            raise FileNotFoundError('Converted DOCX file not found after LibreOffice conversion')

        return output_path, temp_dir

    async def _cleanup_temp_dir(self, temp_dir: Optional[Path]) -> None:
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    async def parse(self, path: Path, options: dict | None = None) -> ParseResult:
        source_path = Path(path)
        if not source_path.exists():
            return ParseResult(
                status=ParseStatus.FAILED,
                metadata=DocumentMetadata(source_path=str(source_path), file_format=FileFormat.DOC, file_size_bytes=0),
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code='not_found', message='DOC file does not exist', recoverable=False)],
                raw_text='',
                cache_hit=False,
                request_id='',
            )

        if source_path.suffix.lower() != '.doc':
            return ParseResult(
                status=ParseStatus.UNSUPPORTED,
                metadata=DocumentMetadata(source_path=str(source_path), file_format=FileFormat.DOC, file_size_bytes=source_path.stat().st_size),
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code='unsupported_format', message='Expected .doc file', recoverable=False)],
                raw_text='',
                cache_hit=False,
                request_id='',
            )

        converted_docx = None
        temp_dir = None
        start = time.time()

        async with libreoffice_semaphore:
            try:
                converted_docx, temp_dir = await self._convert_doc_to_docx(source_path)
            except TimeoutError as exc:
                await self._cleanup_temp_dir(temp_dir)
                return ParseResult(
                    status=ParseStatus.FAILED,
                    metadata=DocumentMetadata(source_path=str(source_path), file_format=FileFormat.DOC, file_size_bytes=source_path.stat().st_size),
                    sections=[],
                    images=[],
                    tables=[],
                    errors=[ParseError(code='conversion_timeout', message=str(exc), recoverable=True)],
                    raw_text='',
                    cache_hit=False,
                    request_id='',
                )
            except Exception as exc:
                await self._cleanup_temp_dir(temp_dir)
                return ParseResult(
                    status=ParseStatus.FAILED,
                    metadata=DocumentMetadata(source_path=str(source_path), file_format=FileFormat.DOC, file_size_bytes=source_path.stat().st_size),
                    sections=[],
                    images=[],
                    tables=[],
                    errors=[ParseError(code='conversion_failed', message=str(exc), recoverable=False)],
                    raw_text='',
                    cache_hit=False,
                    request_id='',
                )

        try:
            delegate = DocxParser()
            result = await delegate.parse(converted_docx, options=options)
        except Exception as exc:
            await self._cleanup_temp_dir(temp_dir)
            return ParseResult(
                status=ParseStatus.FAILED,
                metadata=DocumentMetadata(source_path=str(source_path), file_format=FileFormat.DOC, file_size_bytes=source_path.stat().st_size),
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code='docx_processing_failed', message=str(exc), recoverable=False)],
                raw_text='',
                cache_hit=False,
                request_id='',
            )
        finally:
            await self._cleanup_temp_dir(temp_dir)

        # preserve original DOC context and event timing
        result.metadata.source_path = str(source_path)
        result.metadata.file_format = FileFormat.DOC
        result.metadata.parse_duration_ms = (time.time() - start) * 1000
        return result

    async def parse_metadata(self, path: Path) -> DocumentMetadata:
        source_path = Path(path)
        if not source_path.exists() or source_path.suffix.lower() != '.doc':
            raise FileNotFoundError('DOC file missing or invalid extension')

        converted_docx = None
        temp_dir = None

        async with libreoffice_semaphore:
            converted_docx, temp_dir = await self._convert_doc_to_docx(source_path)

        try:
            delegate = DocxParser()
            metadata = await delegate.parse_metadata(converted_docx)
        finally:
            await self._cleanup_temp_dir(temp_dir)

        metadata.source_path = str(source_path)
        metadata.file_format = FileFormat.DOC
        return metadata
