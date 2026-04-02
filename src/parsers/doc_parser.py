from __future__ import annotations
import asyncio
import os
import shutil
import signal
import subprocess
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
from src.parsers.utils import FileOversizeError, enforce_file_size

LIBREOFFICE_BINARY = os.environ.get("LIBREOFFICE_BINARY", "soffice")
LIBREOFFICE_TIMEOUT_SEC = int(os.environ.get("LIBREOFFICE_TIMEOUT_SEC", "30"))
LIBREOFFICE_SECONDARY_KILL_TIMEOUT_SEC = int(os.environ.get("LIBREOFFICE_SECONDARY_KILL_TIMEOUT_SEC", "5"))
LIBREOFFICE_MAX_CONCURRENT = int(os.environ.get("LIBREOFFICE_MAX_CONCURRENT", "2"))

# Global bounded semaphore to prevent LibreOffice overload and excessive process spawning.
libreoffice_semaphore = asyncio.BoundedSemaphore(LIBREOFFICE_MAX_CONCURRENT)


async def _terminate_process_group(process: asyncio.subprocess.Process) -> None:
    try:
        if process.returncode is not None:
            return

        if os.name == "posix":
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGTERM)
        else:
            # Windows: send CTRL_BREAK_EVENT to process group
            process.send_signal(signal.CTRL_BREAK_EVENT)
        await asyncio.sleep(0.2)

        if process.returncode is None:
            if os.name == "posix":
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGKILL)
            else:
                process.kill()
    except (ProcessLookupError, PermissionError):
        pass
    except Exception:
        pass


async def _run_subprocess(cmd: list[str], timeout: int) -> tuple[bytes, bytes]:
    kwargs = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    if os.name == "posix":
        kwargs["preexec_fn"] = os.setsid
    else:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    process = await asyncio.create_subprocess_exec(*cmd, **kwargs)

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        await _terminate_process_group(process)
        await process.wait()
        raise TimeoutError("LibreOffice conversion timed out") from exc

    if process.returncode != 0:
        raise RuntimeError(
            f"LibreOffice conversion failed (returncode={process.returncode}) stdout={stdout.decode(errors='ignore')} stderr={stderr.decode(errors='ignore')}"
        )

    return stdout, stderr


@register(FileFormat.DOC)
class DocParser(BaseParser):
    async def _convert_doc_to_docx(self, doc_path: Path) -> Tuple[Path, Path]:
        temp_dir = Path(tempfile.mkdtemp(prefix="parsival_docx_"))
        output_path = temp_dir / f"{doc_path.stem}.docx"

        cmd = [
            LIBREOFFICE_BINARY,
            "--headless",
            "--invisible",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--nocrashreport",
            "--convert-to",
            "docx",
            "--outdir",
            str(temp_dir),
            str(doc_path),
        ]

        await _run_subprocess(cmd, timeout=LIBREOFFICE_TIMEOUT_SEC)

        if not output_path.exists():
            raise FileNotFoundError("Converted DOCX file not found after LibreOffice conversion")

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
                errors=[ParseError(code="not_found", message="DOC file does not exist", recoverable=False)],
                raw_text="",
                cache_hit=False,
                request_id="",
            )

        if source_path.suffix.lower() != ".doc":
            return ParseResult(
                status=ParseStatus.UNSUPPORTED,
                metadata=DocumentMetadata(
                    source_path=str(source_path), file_format=FileFormat.DOC, file_size_bytes=source_path.stat().st_size
                ),
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code="unsupported_format", message="Expected .doc file", recoverable=False)],
                raw_text="",
                cache_hit=False,
                request_id="",
            )

        try:
            enforce_file_size(
                source_path,
                max_size_mb=(options or {}).get("max_size_mb"),
                max_stream_size_mb=(options or {}).get("max_stream_file_size_mb"),
            )
        except FileOversizeError as exc:
            return ParseResult(
                status=ParseStatus.OVERSIZE,
                metadata=DocumentMetadata(
                    source_path=str(source_path), file_format=FileFormat.DOC, file_size_bytes=source_path.stat().st_size
                ),
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code="oversize", message=str(exc), recoverable=False)],
                raw_text="",
                cache_hit=False,
                request_id="",
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
                    metadata=DocumentMetadata(
                        source_path=str(source_path),
                        file_format=FileFormat.DOC,
                        file_size_bytes=source_path.stat().st_size,
                    ),
                    sections=[],
                    images=[],
                    tables=[],
                    errors=[ParseError(code="conversion_timeout", message=str(exc), recoverable=True)],
                    raw_text="",
                    cache_hit=False,
                    request_id="",
                )
            except Exception as exc:
                await self._cleanup_temp_dir(temp_dir)
                exc_msg = str(exc)
                code = "conversion_failed"
                if "encrypted" in exc_msg.lower() or "password" in exc_msg.lower():
                    code = "encrypted"
                return ParseResult(
                    status=ParseStatus.FAILED,
                    metadata=DocumentMetadata(
                        source_path=str(source_path),
                        file_format=FileFormat.DOC,
                        file_size_bytes=source_path.stat().st_size,
                    ),
                    sections=[],
                    images=[],
                    tables=[],
                    errors=[ParseError(code=code, message=exc_msg, recoverable=False)],
                    raw_text="",
                    cache_hit=False,
                    request_id="",
                )

        try:
            delegate = DocxParser()
            result = await delegate.parse(converted_docx, options=options)
        except Exception as exc:
            await self._cleanup_temp_dir(temp_dir)
            return ParseResult(
                status=ParseStatus.FAILED,
                metadata=DocumentMetadata(
                    source_path=str(source_path), file_format=FileFormat.DOC, file_size_bytes=source_path.stat().st_size
                ),
                sections=[],
                images=[],
                tables=[],
                errors=[ParseError(code="docx_processing_failed", message=str(exc), recoverable=False)],
                raw_text="",
                cache_hit=False,
                request_id="",
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
        if not source_path.exists() or source_path.suffix.lower() != ".doc":
            raise FileNotFoundError("DOC file missing or invalid extension")

        converted_docx = None
        temp_dir = None

        try:
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
        except FileNotFoundError as exc:
            # LibreOffice not installed / converter missing: return lightweight metadata without parse
            return DocumentMetadata(
                source_path=str(source_path),
                file_format=FileFormat.DOC,
                file_size_bytes=source_path.stat().st_size,
                section_count=0,
                table_count=0,
                image_count=0,
                has_toc=False,
                toc=[],
                parse_duration_ms=0.0,
            )
        except Exception as exc:
            # Fallback metadata on any converter failure
            return DocumentMetadata(
                source_path=str(source_path),
                file_format=FileFormat.DOC,
                file_size_bytes=source_path.stat().st_size,
                section_count=0,
                table_count=0,
                image_count=0,
                has_toc=False,
                toc=[],
                parse_duration_ms=0.0,
            )

        metadata.source_path = str(source_path)
        metadata.file_format = FileFormat.DOC
        return metadata
