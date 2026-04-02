import asyncio
import os
import tempfile
from pathlib import Path

from mcp import ClientSessionGroup
from mcp.client.session_group import SseServerParameters


async def run_smoke_test():
    # Create support file (TXT) and unsupported file (binary extension).  
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
        f.write("Parsival smoke test\nline2")
        text_path = f.name

    with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".bin") as f:
        f.write(b"\x00\x01\x02\x03")
        bin_path = f.name

    print("text file:", text_path)
    print("binary file:", bin_path)

    async with ClientSessionGroup() as group:
        params = SseServerParameters(url="http://127.0.0.1:6969/sse")
        server = await group.connect_to_server(params)

        print("connected to MCP server:", server)

        tools = list(group.tools.keys())
        print(f"discovered {len(tools)} tool(s):", tools)

        async def call_tool(name, args):
            try:
                result = await group.call_tool(name, args)
                print(f"PASS {name} -> type={type(result).__name__}, has errors={result.isError}")
                if hasattr(result, 'result'):
                    print('  result:', result.result)
                return True
            except Exception as exc:
                print(f"FAIL {name}: {exc.__class__.__name__}: {exc}")
                return False

        await call_tool("read_file", {"path": text_path, "output_format": "text"})
        await call_tool("convert_to_markdown", {"path": text_path})
        await call_tool("search_file", {"path": text_path, "query": "Parsival", "top_k": 5})
        await call_tool("get_metadata", {"path": text_path})
        await call_tool("extract_images", {"path": text_path})

        # expected to fail on bin content for read_file text path
        await call_tool("read_file", {"path": bin_path, "output_format": "text"})

        try:
            await call_tool("extract_table", {"path": text_path, "table_index": 1})
        except Exception:
            pass

    os.remove(text_path)
    os.remove(bin_path)


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
