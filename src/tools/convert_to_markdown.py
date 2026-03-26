from src.tools.read_file import _read_file
from src.models.enums import OutputFormat


async def convert_to_markdown(path: str) -> str:
    result = await _read_file(path, output_format=OutputFormat.MARKDOWN)
    return result.content
