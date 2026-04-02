from typing import Any, Optional, Tuple, List

from src.core.logging import get_logger
from src.post_processors.pipeline import PostProcessingPipeline
from src.serialisers.markdown import MarkdownSerializer
from src.serialisers.json_serializer import JSONSerializer
from src.serialisers.text_serializer import TextSerializer
from src.parsers.registry import get_parser
from src.core.router import FormatRouter, UnsupportedFormatError
from src.core.cache import ContentHashStore
from src.core.executor import run_parse_in_pool
from src.models.enums import OutputFormat
from src.models.tool_responses import SearchHit
from src.models.metadata import DocumentMetadata
from src.models.table import TableResult
from src.models.image import ImageRef
from src.mcp_runtime import initialize_cache, parse_file_core, serialize_result_core

# Singleton instances
logger = get_logger("parsival")
cache_store = ContentHashStore(max_bytes=500 * 1024 * 1024)


async def _startup():
    """Application startup initialization."""
    await initialize_cache(cache_store)


def get_cache():
    """Returns the global cache store."""
    return cache_store


async def parse_file(
    path: str,
    output_format: OutputFormat = OutputFormat.MARKDOWN,
    page_range: tuple[int, int] | None = None,
    include_images: bool = True,
    max_tokens_hint: int | None = None,
    stream: bool = False,
):
    """Core parsing orchestration logic."""
    # Keep dependency bindings local so tests can monkeypatch app-level collaborators.
    return await parse_file_core(
        path,
        output_format=output_format,
        page_range=page_range,
        include_images=include_images,
        max_tokens_hint=max_tokens_hint,
        stream=stream,
        startup_cb=_startup,
        logger=logger,
        format_router_factory=FormatRouter,
        unsupported_format_error=UnsupportedFormatError,
        get_parser_fn=get_parser,
        cache_store=cache_store,
        run_parse_in_pool_fn=run_parse_in_pool,
        postprocess_run_fn=PostProcessingPipeline.run,
    )


def serialize_result(result, output_format: OutputFormat) -> str:
    """Serializes ParseResult to the requested string format."""
    return serialize_result_core(
        result,
        output_format,
        markdown_serializer=MarkdownSerializer,
        json_serializer=JSONSerializer,
        text_serializer=TextSerializer,
    )


# --- Tool Callables ---


async def read_file(
    path: str,
    output_format: str = "markdown",
    page_range: list[int] | None = None,
    include_images: bool = True,
    max_tokens_hint: int | None = None,
    stream: bool = False,
) -> Any:
    """
    Parses any document and returns its contents.
    Supported: PDF, DOCX, XLSX, TXT, MD, CSV, HTML.
    """
    from src.tools.read_file import _read_file

    fmt = OutputFormat(output_format.lower())
    page_range_tuple: tuple[int, int] | None = None
    if page_range is not None:
        if len(page_range) != 2:
            raise ValueError("page_range must contain exactly two integers")
        page_range_tuple = (page_range[0], page_range[1])
    return await _read_file(
        path,
        output_format=fmt,
        page_range=page_range_tuple,
        include_images=include_images,
        max_tokens_hint=max_tokens_hint,
        stream=stream,
    )


async def get_metadata(path: str) -> DocumentMetadata:
    """Extracts summary metadata (author, pages, dates) from a file."""
    from src.tools.get_metadata import get_metadata as _get_meta

    return await _get_meta(path)


async def extract_table(path: str, table_index: int = 1, sheet_name: Optional[str] = None) -> TableResult:
    """Extracts a specific table or spreadsheet sheet by index."""
    from src.tools.extract_table import extract_table as _ext_table

    return await _ext_table(path, table_index, sheet_name)


async def extract_images(
    path: str, page_range: Optional[Tuple[int, int]] = None, max_dimension: Optional[int] = None
) -> List[ImageRef]:
    """Extracts all embedded images from a document."""
    from src.tools.extract_images import extract_images as _ext_images

    return await _ext_images(path, page_range, max_dimension)


async def search_file(path: str, query: str, top_k: int = 5) -> List[SearchHit]:
    """Semantic BM25 search within a specific document's text."""
    from src.tools.search_file import search_file as _search

    return await _search(path, query, top_k)


async def convert_to_markdown(path: str) -> str:
    """Convenience tool to get raw markdown string for a file."""
    from src.tools.convert_to_markdown import convert_to_markdown as _conv

    return await _conv(path)


def list_supported_formats() -> dict:
    """Lists all file formats this parser can handle."""
    from src.tools.list_supported_formats import list_supported_formats_tool

    return list_supported_formats_tool()


TOOL_FUNCTIONS = {
    "read_file": read_file,
    "get_metadata": get_metadata,
    "extract_table": extract_table,
    "extract_images": extract_images,
    "search_file": search_file,
    "convert_to_markdown": convert_to_markdown,
    "list_supported_formats": list_supported_formats,
}
