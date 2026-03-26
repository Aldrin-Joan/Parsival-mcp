from fastmcp import FastMCP
from pathlib import Path
from src.config import settings
from src.core.logging import get_logger
from src.parsers import registry  # ensure parser modules are imported
from src.post_processors.pipeline import PostProcessingPipeline
from src.serialisers.markdown import MarkdownSerializer
from src.parsers.registry import get_parser
from src.core.router import FormatRouter
from src.core.cache import ContentHashStore
from src.models.enums import OutputFormat
from src.models.parse_result import ParseResult
import src.tools  # register tools

logger = get_logger('parsival')

cache_store = ContentHashStore(max_bytes=500 * 1024 * 1024)

mcp = FastMCP('Parsival', version='0.1.0')

# Tool registration should be done by importing src.tools module from entrypoint.


def get_cache():
    return cache_store


def detect_format(path: str):
    return FormatRouter().detect(path)


async def parse_file(path: str, output_format: OutputFormat = OutputFormat.MARKDOWN, stream: bool = False):
    fmt = detect_format(path)
    parser = get_parser(fmt)
    cache = get_cache()
    options = {'output_format': output_format.value, 'stream': stream}
    key = cache.make_cache_key(path, options)

    hit = None
    if not stream:
        hit = await cache.get(key)
    if hit:
        hit.metadata = hit.metadata.model_copy(update={'parse_duration_ms': 0.0})
        hit.cache_hit = True
        return hit

    result = await parser.parse(Path(path))
    result = PostProcessingPipeline.run(result)

    if not stream:
        await cache.set(key, result)

    return result


def serialize_result(result, output_format: OutputFormat):
    if output_format == OutputFormat.MARKDOWN:
        return MarkdownSerializer.serialize(result)
    elif output_format == OutputFormat.JSON:
        return result.model_dump_json(indent=2, exclude_none=True)
    else:
        return result.raw_text or ''
