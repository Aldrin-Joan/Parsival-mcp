from src.parsers.registry import list_supported_formats
from src.app import mcp


def list_supported_formats_tool():
    formats = list_supported_formats()
    return {
        'server_version': mcp.version,
        'formats': [fmt.value for fmt in formats],
        'count': len(formats),
    }
