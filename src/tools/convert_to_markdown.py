from src.models.enums import OutputFormat
from src.models.enums import ParseStatus
from src.tools.read_file import _read_file
from src.core.logging import get_logger

logger = get_logger(__name__)


async def convert_to_markdown(path: str) -> str:
    """
    Directly converts a file to Markdown string.

    Args:
        path: Validated path to the file.

    Returns:
        Markdown content as a string.
    """
    logger.info("tool_convert_to_markdown", path=path)
    result = await _read_file(path, output_format=OutputFormat.MARKDOWN)
    if result.status in (ParseStatus.FAILED, ParseStatus.UNSUPPORTED, ParseStatus.OVERSIZE):
        reason = result.errors[0].message if result.errors else f"status={result.status.value}"
        raise ValueError(f"convert_to_markdown_failed: {reason}")

    raw_content = result.content or ""
    if not raw_content.strip():
        raise ValueError("convert_to_markdown_empty_output")
    return raw_content
