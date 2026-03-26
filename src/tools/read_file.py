from pathlib import Path
from src.models.enums import OutputFormat
from src.models.tool_responses import ReadFileResult
from src.app import parse_file, serialize_result


async def _read_file(
    path: str,
    output_format: OutputFormat = OutputFormat.MARKDOWN,
    stream: bool = False,
) -> ReadFileResult:
    result = await parse_file(path, output_format=output_format, stream=stream)

    if stream:
        raise NotImplementedError('stream path not implemented in tool wrapper')

    content = serialize_result(result, output_format)
    return ReadFileResult(
        status=result.status,
        format=output_format,
        content=content,
        metadata=result.metadata,
        errors=result.errors,
        cache_hit=result.cache_hit,
        request_id=result.request_id or '',
    )
