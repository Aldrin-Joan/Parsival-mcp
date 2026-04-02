from pathlib import Path
from typing import Any, Callable

from src.models.enums import FileFormat, OutputFormat, ParseStatus
from src.models.metadata import DocumentMetadata
from src.models.parse_result import ParseError, ParseResult


async def initialize_cache(cache_store: Any) -> None:
    """Initializes shared cache resources once per process lifecycle."""
    await cache_store.initialize()


async def parse_file_core(
    path: str,
    output_format: OutputFormat,
    page_range: tuple[int, int] | None,
    include_images: bool,
    max_tokens_hint: int | None,
    stream: bool,
    *,
    startup_cb: Callable[[], Any],
    logger: Any,
    format_router_factory: Callable[[], Any],
    unsupported_format_error: type[Exception],
    get_parser_fn: Callable[[Any], Any],
    cache_store: Any,
    run_parse_in_pool_fn: Callable[..., Any],
    postprocess_run_fn: Callable[[Any], Any],
) -> Any:
    """Transport-agnostic parse orchestration used by all server entrypoints."""
    try:
        # Startup is invoked defensively so every transport path can share init behavior.
        await startup_cb()
    except Exception as exc:
        logger.warning("startup_initialization_failed", error=str(exc))

    file_path = Path(path)
    pre_stat = file_path.stat()

    try:
        fmt = format_router_factory().detect(path)
    except unsupported_format_error as exc:
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

    parser = get_parser_fn(fmt)
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

    res = await run_parse_in_pool_fn(path, options=opts)
    res = postprocess_run_fn(res)

    if max_tokens_hint is not None and max_tokens_hint > 0 and res.raw_text:
        tokens = res.raw_text.split()
        if len(tokens) > max_tokens_hint:
            res.raw_text = " ".join(tokens[:max_tokens_hint])
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


def serialize_result_core(
    result: Any,
    output_format: OutputFormat,
    *,
    markdown_serializer: Any,
    json_serializer: Any,
    text_serializer: Any,
) -> str:
    """Serializes ParseResult using the configured serializers."""
    if output_format == OutputFormat.MARKDOWN:
        return markdown_serializer.serialize(result)
    if output_format == OutputFormat.JSON:
        return json_serializer.serialize(result)
    if output_format == OutputFormat.TEXT:
        return text_serializer.serialize(result)
    return result.raw_text or ""
