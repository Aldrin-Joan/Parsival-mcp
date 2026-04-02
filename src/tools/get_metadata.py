import time
from src.parsers.registry import get_parser
from src.core.router import FormatRouter, UnsupportedFormatError
from src.models.enums import FileFormat
from src.models.metadata import DocumentMetadata
from src.core.security import validate_safe_path
from src.core.logging import get_logger

logger = get_logger(__name__)


async def get_metadata(path: str) -> DocumentMetadata:
    """
    Extracts metadata from a file without full parsing.

    Args:
        path: Validated path to the file.

    Returns:
        DocumentMetadata object.
    """
    # 1. Security check
    safe_path = validate_safe_path(path)

    logger.info("tool_get_metadata_start", path=str(safe_path))

    # 2. Execution
    try:
        fmt = FormatRouter().detect(str(safe_path))
        parser = get_parser(fmt)

        start = time.perf_counter()
        metadata = await parser.parse_metadata(safe_path)
        duration_ms = (time.perf_counter() - start) * 1000

        metadata.parse_duration_ms = duration_ms

        logger.info("tool_get_metadata_complete", path=str(safe_path), duration_ms=duration_ms)

        return metadata
    except UnsupportedFormatError:
        metadata = DocumentMetadata(
            source_path=str(safe_path),
            file_format=FileFormat.UNKNOWN,
            file_size_bytes=safe_path.stat().st_size,
            section_count=0,
            table_count=0,
            image_count=0,
            has_toc=False,
            toc=[],
            parse_duration_ms=0.0,
            parser_version="",
        )
        logger.info("tool_get_metadata_unsupported", path=str(safe_path))
        return metadata
