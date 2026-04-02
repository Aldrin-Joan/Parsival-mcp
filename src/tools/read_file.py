from src.models.enums import OutputFormat
from src.models.tool_responses import ReadFileResult
from src.core.security import validate_safe_path
from src.core.logging import get_logger

logger = get_logger(__name__)


async def _read_file(
    path: str,
    output_format: OutputFormat = OutputFormat.MARKDOWN,
    stream: bool = False,
) -> ReadFileResult:
    """
    Parses a file and returns its content in the specified format.

    Args:
        path: Validated absolute or relative path to the file.
        output_format: Desired output format (markdown or json).
        stream: Whether to stream sections as chunks.

    Returns:
        ReadFileResult containing parsed content and metadata.
    """
    from src.app import parse_file, serialize_result

    # 1. Security boundary check
    safe_path = validate_safe_path(path)

    logger.info(
        "tool_read_file_start",
        path=str(safe_path),
        format=output_format.value
    )

    # 2. Execution
    result = await parse_file(
        str(safe_path),
        output_format=output_format,
        stream=stream
    )

    if stream:
        # Stream mode returns an async iterator of StreamChunk
        logger.debug("tool_read_file_streaming", path=str(safe_path))
        return result

    # 3. Serialization & Response
    content = serialize_result(result, output_format)

    logger.info(
        "tool_read_file_complete",
        path=str(safe_path),
        sections=len(result.sections)
    )

    return ReadFileResult(
        status=result.status,
        format=output_format,
        content=content,
        metadata=result.metadata,
        errors=result.errors,
        cache_hit=result.cache_hit,
        request_id=result.request_id or '',
    )


