import asyncio
import os
import tempfile
from pathlib import Path

from src.app import (
    convert_to_markdown,
    extract_images,
    extract_table,
    get_metadata,
    list_supported_formats,
    read_file,
    search_file,
)


async def safe_call(name, fn, *args, **kwargs):
    try:
        result = await fn(*args, **kwargs)
        print(f"[PASS] {name}: type={type(result).__name__}")
        if isinstance(result, (str, list, dict)):
            print("    ->", result if len(str(result)) < 400 else str(result)[:400] + "...")
        else:
            print("    -> <non-printable result>")
    except Exception as exc:
        print(f"[FAIL] {name}: {exc.__class__.__name__}: {exc}")


async def smoke_test():
    print("=== Tool registration check ===")
    try:
        formats = list_supported_formats()
        print(f"[PASS] list_supported_formats -> {len(formats)} formats")
    except Exception as e:
        print(f"[FAIL] list_supported_formats: {e}")

    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".txt") as tf:
        tf.write("Hello Parsival tool smoke test.\nThis is line two.\n")
        tf.flush()
        path = tf.name

    try:
        print("\n=== Running each tool on sample TXT file ===")
        await safe_call("read_file", read_file, path, output_format="text")
        await safe_call("convert_to_markdown", convert_to_markdown, path)
        await safe_call("search_file", search_file, path, "Parsival", top_k=3)

        # For non-text tools we call and catch failure no-op
        await safe_call("get_metadata", get_metadata, path)
        try:
            await safe_call("extract_images", extract_images, path)
        except Exception as exc:
            print("    (expected: some formats may not contain images)", exc)
        try:
            await safe_call("extract_table", extract_table, path, 1)
        except Exception as exc:
            print("    (expected: table extraction may fail for text)", exc)

    finally:
        os.remove(path)


if __name__ == "__main__":
    asyncio.run(smoke_test())
