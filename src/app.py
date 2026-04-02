from typing import Any, Optional, Tuple, List
from fastmcp import FastMCP
from pathlib import Path

from src.core.logging import get_logger
from src.post_processors.pipeline import PostProcessingPipeline
from src.serialisers.markdown import MarkdownSerializer
from src.serialisers.json_serializer import JSONSerializer
from src.serialisers.text_serializer import TextSerializer
from src.parsers.registry import get_parser
from src.core.router import FormatRouter, UnsupportedFormatError
from src.core.cache import ContentHashStore
from src.core.executor import run_parse_in_pool
from src.models.enums import FileFormat, OutputFormat, ParseStatus
from src.models.tool_responses import SearchHit
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseResult, ParseError
from src.models.table import TableResult
from src.models.image import ImageRef

# Singleton instances
logger = get_logger("parsival")
cache_store = ContentHashStore(max_bytes=500 * 1024 * 1024)
mcp = FastMCP("Parsival", version="0.1.0")


async def _startup():
    """Application startup initialization."""
    await cache_store.initialize()


if hasattr(mcp, "on_startup"):

    @mcp.on_startup
    async def startup_hook():
        await _startup()
else:
    logger.warning("mcp_on_startup_not_available", message="FastMCP on_startup hook not available in this version")


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
    try:
        await _startup()
    except Exception as exc:
        logger.warning("startup_initialization_failed", error=str(exc))

    file_path = Path(path)
    pre_stat = file_path.stat()

    try:
        fmt = FormatRouter().detect(path)
    except UnsupportedFormatError as exc:
        metadata = DocumentMetadata(
            source_path=str(path),
            file_format=FileFormat.UNKNOWN,
            file_size_bytes=pre_stat.st_size,
            section_count=0,
            table_count=0,
            image_count=0,
            has_toc=False,
            toc=[],
            parse_duration_ms=0.0,
            parser_version="",
        )
        return ParseResult(
            status=ParseStatus.UNSUPPORTED,
            metadata=metadata,
            sections=[],
            images=[],
            tables=[],
            errors=[ParseError(code="unsupported_format", message=str(exc), recoverable=False)],
            raw_text="",
            cache_hit=False,
            request_id="",
        )

    parser = get_parser(fmt)
    opts = {
        "output_format": output_format.value,
        "stream": stream,
        "page_range": page_range,
        "include_images": include_images,
        "max_tokens_hint": max_tokens_hint,
    }
    key = cache_store.make_cache_key(path, opts)

    if not stream:
        hit = await cache_store.get(key)
        if hit:
            hit.metadata.parse_duration_ms = 0.0
            hit.cache_hit = True
            return hit

    if stream:
        return parser.stream_chunks(file_path, options=opts)

    res = await run_parse_in_pool(path, options=opts)
    res = PostProcessingPipeline.run(res)

    # Apply token hint post hoc (soft limit)
    if max_tokens_hint is not None and max_tokens_hint > 0 and res.raw_text:
        tokens = res.raw_text.split()
        if len(tokens) > max_tokens_hint:
            res.raw_text = " ".join(tokens[:max_tokens_hint])
            # trim section list to match text budget
            token_count = 0
            kept_sections = []

            for sec in res.sections:
                sec_tokens = sec.content.split()
                if token_count + len(sec_tokens) <= max_tokens_hint:
                    kept_sections.append(sec)
                    token_count += len(sec_tokens)
                else:
                    break
            res.sections = kept_sections
            res.status = ParseStatus.PARTIAL
            res.errors.append(
                ParseError(
                    code="max_tokens_hint_reached",
                    message=f"Truncated output to {max_tokens_hint} tokens",
                    recoverable=True,
                )
            )

    post_stat = file_path.stat()
    if post_stat.st_mtime != pre_stat.st_mtime or post_stat.st_size != pre_stat.st_size:
        res.errors.append(
            ParseError(
                code="file_modified_during_parse",
                message="File mtime changed during parsing; result may be inconsistent",
                recoverable=True,
            )
        )
        res.status = ParseStatus.PARTIAL
        await cache_store.invalidate(key)
        return res

    if not stream:
        await cache_store.set(key, res)
    return res


def serialize_result(result, output_format: OutputFormat) -> str:
    """Serializes ParseResult to the requested string format."""
    if output_format == OutputFormat.MARKDOWN:
        return MarkdownSerializer.serialize(result)
    if output_format == OutputFormat.JSON:
        return JSONSerializer.serialize(result)
    if output_format == OutputFormat.TEXT:
        return TextSerializer.serialize(result)
    return result.raw_text or ""


# --- MCP Tool Registrations ---


@mcp.tool()
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


@mcp.tool()
async def get_metadata(path: str) -> DocumentMetadata:
    """Extracts summary metadata (author, pages, dates) from a file."""
    from src.tools.get_metadata import get_metadata as _get_meta

    return await _get_meta(path)


@mcp.tool()
async def extract_table(path: str, table_index: int = 1, sheet_name: Optional[str] = None) -> TableResult:
    """Extracts a specific table or spreadsheet sheet by index."""
    from src.tools.extract_table import extract_table as _ext_table

    return await _ext_table(path, table_index, sheet_name)


@mcp.tool()
async def extract_images(
    path: str, page_range: Optional[Tuple[int, int]] = None, max_dimension: Optional[int] = None
) -> List[ImageRef]:
    """Extracts all embedded images from a document."""
    from src.tools.extract_images import extract_images as _ext_images

    return await _ext_images(path, page_range, max_dimension)


@mcp.tool()
async def search_file(path: str, query: str, top_k: int = 5) -> List[SearchHit]:
    """Semantic BM25 search within a specific document's text."""
    from src.tools.search_file import search_file as _search

    return await _search(path, query, top_k)


@mcp.tool()
async def convert_to_markdown(path: str) -> str:
    """Convenience tool to get raw markdown string for a file."""
    from src.tools.convert_to_markdown import convert_to_markdown as _conv

    return await _conv(path)


@mcp.tool()
def list_supported_formats() -> dict:
    """Lists all file formats this parser can handle."""
    from src.tools.list_supported_formats import list_supported_formats_tool

    return list_supported_formats_tool()
