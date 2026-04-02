from src.parsers.registry import list_supported_formats
from src.core.logging import get_logger

logger = get_logger(__name__)


def list_supported_formats_tool():
    """
    Returns the list of all file formats supported by Parsival.

    Returns:
        Dict containing supported formats and server info.
    """
    logger.info("tool_list_formats_start")
    formats = list_supported_formats()

    try:
        from src import __version__ as server_version
    except ImportError:
        server_version = "unknown"

    res = {
        "formats": [fmt.value for fmt in formats],
        "count": len(formats),
        "server_version": server_version,
    }

    logger.info("tool_list_formats_complete", count=len(formats))
    return res
