from __future__ import annotations
import os
import asyncio
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from src.config import settings
from src.core.router import FormatRouter
from src.parsers.registry import get_parser

CPU_COUNT = os.cpu_count() or 1
MAX_WORKERS = min(settings.PROCESS_POOL_SIZE, max(1, CPU_COUNT - 1))

# avoid oversubscription for multithreaded libs
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

_executor: ProcessPoolExecutor | None = None


def get_process_pool() -> ProcessPoolExecutor:
    global _executor
    if _executor is None or (hasattr(_executor, "_shutdown") and _executor._shutdown):
        _executor = ProcessPoolExecutor(max_workers=MAX_WORKERS)
    return _executor


def parse_file_worker(path: str, options: dict | None = None) -> Any:
    """Worker function executed in a process pool."""
    fmt = FormatRouter().detect(path)
    parser = get_parser(fmt)
    # parser.parse is async; run in local loop inside worker.
    result = asyncio.run(parser.parse(Path(path), options=options))
    return result


async def run_parse_in_pool(path: str, options: dict | None = None) -> Any:
    loop = asyncio.get_running_loop()
    executor = get_process_pool()
    return await loop.run_in_executor(executor, parse_file_worker, path, options)
