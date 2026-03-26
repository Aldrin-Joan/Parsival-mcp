import asyncio
from pathlib import Path

import pytest

from src.parsers.text_parser import TextParser


def _write_file(path: Path, size_mb: int):
    line = "The quick brown fox jumps over the lazy dog.\n"
    with path.open("w", encoding="utf-8") as f:
        while path.stat().st_size < size_mb * 1024 * 1024:
            f.write(line)


@pytest.mark.asyncio
async def test_benchmark_parse_latency_small(request, tmp_path):
    source = tmp_path / "small.txt"
    source.write_text("hello world\n" * 1000, encoding="utf-8")

    parser = TextParser()

    async def bench_fn():
        result = await parser.parse(source)
        assert result.status == "ok"

    if request.config.pluginmanager.has_plugin("pytest_benchmark"):
        benchmark = request.getfixturevalue("benchmark")
        await benchmark(bench_fn)
    else:
        # Fallback behavior when pytest-benchmark not installed
        import time
        durations = []
        for _ in range(5):
            start = time.perf_counter()
            await bench_fn()
            durations.append(time.perf_counter() - start)
        print("small parse durations", durations)


@pytest.mark.asyncio
async def test_benchmark_parse_latency_large(request, tmp_path):
    source = tmp_path / "large.txt"
    _write_file(source, size_mb=55)

    parser = TextParser()

    async def bench_fn():
        result = await parser.parse(source)
        assert result.status == "ok"

    if request.config.pluginmanager.has_plugin("pytest_benchmark"):
        benchmark = request.getfixturevalue("benchmark")
        await benchmark(bench_fn)
    else:
        import time
        durations = []
        for _ in range(3):
            start = time.perf_counter()
            await bench_fn()
            durations.append(time.perf_counter() - start)
        print("large parse durations", durations)


@pytest.mark.asyncio
async def test_benchmark_streaming_first_chunk(request, tmp_path):
    source = tmp_path / "stream.txt"
    source.write_text("Line\n" * 50000, encoding="utf-8")

    parser = TextParser()

    async def bench_fn():
        stream = parser.stream_sections(source)
        first = None
        async for section in stream:
            first = section
            break
        if first is not None:
            await stream.aclose()
        assert first is not None

    if request.config.pluginmanager.has_plugin("pytest_benchmark"):
        benchmark = request.getfixturevalue("benchmark")
        await benchmark(bench_fn)
    else:
        import time
        durations = []
        for _ in range(5):
            start = time.perf_counter()
            await bench_fn()
            durations.append(time.perf_counter() - start)
        print("stream first-chunk durations", durations)


@pytest.mark.asyncio
async def test_benchmark_throughput_concurrent(request, tmp_path):
    source = tmp_path / "parallel.txt"
    source.write_text("hello world\n" * 20000, encoding="utf-8")

    parser = TextParser()

    async def bench_fn():
        tasks = [asyncio.create_task(parser.parse(source)) for _ in range(10)]
        results = await asyncio.gather(*tasks)
        assert all(r.status == "ok" for r in results)

    if request.config.pluginmanager.has_plugin("pytest_benchmark"):
        benchmark = request.getfixturevalue("benchmark")
        await benchmark(bench_fn)
    else:
        import time
        durations = []
        for _ in range(5):
            start = time.perf_counter()
            await bench_fn()
            durations.append(time.perf_counter() - start)
        print("parallel throughput durations", durations)
