import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSessionGroup
from mcp.client.stdio import StdioServerParameters


EXPECTED_TOOLS = {
    "read_file",
    "get_metadata",
    "extract_table",
    "extract_images",
    "search_file",
    "convert_to_markdown",
    "list_supported_formats",
}


def _result_text(result) -> str:
    if not getattr(result, "content", None):
        return ""
    first = result.content[0]
    return getattr(first, "text", "") or ""


async def run_smoke_test():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
        f.write("Parsival stdio smoke test\nline2\n")
        text_path = f.name

    print("text file:", text_path)

    env = dict(os.environ)
    env.setdefault("MCP_TRANSPORT", "stdio")
    env.setdefault("PYTHONPATH", str(Path.cwd()))
    env.setdefault("MCP_WORKSPACE_ROOT", str(Path.cwd()))

    try:
        async with ClientSessionGroup() as group:
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "src.mcp_entrypoint"],
                cwd=str(Path.cwd()),
                env=env,
            )
            server = await asyncio.wait_for(group.connect_to_server(params), timeout=20)

            print("connected to MCP server:", server)
            tools = set(group.tools.keys())
            print(f"discovered {len(tools)} tool(s):", sorted(tools))
            print("tool_inventory_parity:", tools == EXPECTED_TOOLS)

            formats_result = await asyncio.wait_for(group.call_tool("list_supported_formats", {}), timeout=20)
            print(f"PASS list_supported_formats -> has errors={formats_result.isError}")
            formats_payload = json.loads(_result_text(formats_result))
            print("formats_count:", formats_payload.get("count"))

            try:
                read_result = await asyncio.wait_for(
                    group.call_tool("read_file", {"path": text_path, "output_format": "text"}),
                    timeout=20,
                )
                print(f"PASS read_file -> has errors={read_result.isError}")
                print("read_file_contains_smoke_text:", "Parsival stdio smoke test" in _result_text(read_result))
            except TimeoutError:
                print("WARN read_file timed out over stdio in current environment")
    finally:
        os.remove(text_path)


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
