from __future__ import annotations
import os
import asyncio
import multiprocessing
from concurrent.futures.process import BrokenProcessPool
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from src.config import settings
from src.core.router import FormatRouter
from src.parsers.registry import get_parser

CPU_COUNT = os.cpu_count() or 1
_configured_workers = max(2, min(int(settings.PROCESS_POOL_SIZE), 4))
MAX_WORKERS = min(_configured_workers, max(1, CPU_COUNT - 1))
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 0.2

# avoid oversubscription for multithreaded libs
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

_executor: ProcessPoolExecutor | None = None


def _worker_initializer() -> None:
    # Defensive for frozen Windows builds and packaged execution.
    multiprocessing.freeze_support()


def get_process_pool() -> ProcessPoolExecutor:
    global _executor
    if _executor is None or (hasattr(_executor, "_shutdown") and _executor._shutdown):
        _executor = ProcessPoolExecutor(
            max_workers=MAX_WORKERS,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_worker_initializer,
        )
    return _executor


def reset_process_pool() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None


def parse_file_worker(path: str, options: dict | None = None) -> Any:
    """Worker function executed in a process pool."""
    fmt = FormatRouter().detect(path)
    parser = get_parser(fmt)
    # parser.parse is async; run in local loop inside worker.
    result = asyncio.run(parser.parse(Path(path), options=options))
    return result


async def run_parse_in_pool(path: str, options: dict | None = None) -> Any:
    loop = asyncio.get_running_loop()
    last_error: Exception | None = None

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        executor = get_process_pool()
        try:
            return await loop.run_in_executor(executor, parse_file_worker, path, options)
        except (BrokenProcessPool, RuntimeError) as exc:
            last_error = exc
            reset_process_pool()
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            raise
        except Exception as exc:
            last_error = exc
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            raise

    if last_error is not None:
        raise last_error

    raise RuntimeError("Process pool execution failed without an explicit error")
