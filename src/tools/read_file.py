from src.models.enums import OutputFormat, ParseStatus, FileFormat
from src.models.parse_result import ParseError
from src.models.metadata import DocumentMetadata
from src.models.tool_responses import ReadFileResult
from src.core.security import validate_safe_path
from src.core.logging import get_logger

logger = get_logger(__name__)


async def _read_file(
    path: str,
    output_format: OutputFormat = OutputFormat.MARKDOWN,
    page_range: tuple[int, int] | None = None,
    include_images: bool = True,
    max_tokens_hint: int | None = None,
    stream: bool = False,
):
    """
    Parses a file and returns its content in the specified format.

    Args:
        path: Validated absolute or relative path to the file.
        output_format: Desired output format (markdown, json, text).
        stream: Whether to stream sections as chunks.

    Returns:
        ReadFileResult or AsyncIterator[StreamChunk] depending on stream flag.
    """
    from src.app import parse_file, serialize_result

    # 1. Security boundary check
    safe_path = validate_safe_path(path)

    logger.info(
        "tool_read_file_start",
        path=str(safe_path),
        format=output_format.value,
        streaming=stream,
    )

    # Validate optional parameters
    if page_range is not None:
        if (
            not isinstance(page_range, (tuple, list))
            or len(page_range) != 2
            or not all(isinstance(x, int) for x in page_range)
            or page_range[0] < 1
            or page_range[1] < page_range[0]
        ):
            error = ParseError(code="invalid_argument", message="page_range must be [start,end] with 1<=start<=end", recoverable=False)
            return ReadFileResult(
                status=ParseStatus.FAILED,
                format=output_format,
                content="",
                metadata=DocumentMetadata(source_path=str(safe_path), file_format=FileFormat.UNKNOWN, file_size_bytes=0),
                errors=[error],
                cache_hit=False,
                request_id="",
            )

    if not isinstance(include_images, bool):
        error = ParseError(code="invalid_argument", message="include_images must be a boolean", recoverable=False)
        return ReadFileResult(
            status=ParseStatus.FAILED,
            format=output_format,
            content="",
            metadata=DocumentMetadata(source_path=str(safe_path), file_format=FileFormat.UNKNOWN, file_size_bytes=0),
            errors=[error],
            cache_hit=False,
            request_id="",
        )

    if max_tokens_hint is not None:
        if not isinstance(max_tokens_hint, int) or max_tokens_hint <= 0:
            error = ParseError(code="invalid_argument", message="max_tokens_hint must be a positive integer", recoverable=False)
            return ReadFileResult(
                status=ParseStatus.FAILED,
                format=output_format,
                content="",
                metadata=DocumentMetadata(source_path=str(safe_path), file_format=FileFormat.UNKNOWN, file_size_bytes=0),
                errors=[error],
                cache_hit=False,
                request_id="",
            )

    # 2. Execution
    result = await parse_file(
        str(safe_path),
        output_format=output_format,
        page_range=page_range,
        include_images=include_images,
        max_tokens_hint=max_tokens_hint,
        stream=stream,
    )

    if stream:
        # Stream mode returns an async iterator of StreamChunk
        logger.debug("tool_read_file_streaming", path=str(safe_path))
        return result

    # 3. Serialization & Response
    if result.status == ParseStatus.UNSUPPORTED:
        content = ""
    else:
        content = serialize_result(result, output_format)

    logger.info(
        "tool_read_file_complete",
        path=str(safe_path),
        sections=len(result.sections),
        cache_hit=result.cache_hit,
    )

    return ReadFileResult(
        status=result.status,
        format=output_format,
        content=content,
        metadata=result.metadata,
        errors=result.errors,
        cache_hit=result.cache_hit,
        request_id=result.request_id or "",
    )
