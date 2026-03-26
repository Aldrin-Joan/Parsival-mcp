from pathlib import Path
import time

from src.parsers.registry import get_parser
from src.core.router import FormatRouter
from src.models.metadata import DocumentMetadata


async def get_metadata(path: str) -> DocumentMetadata:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"File not found: {path}")

    fmt = FormatRouter().detect(path)
    parser = get_parser(fmt)

    start = time.perf_counter()
    metadata = await parser.parse_metadata(source)
    duration_ms = (time.perf_counter() - start) * 1000

    metadata.parse_duration_ms = duration_ms
    return metadata
