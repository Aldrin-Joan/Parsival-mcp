import asyncio
import importlib
import inspect
import json
import logging
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool

try:
    from src import app as app_module
except ModuleNotFoundError:
    # Allow `python src/mcp_stdio.py` from repository root by adding parent to sys.path.
    project_root = str(Path(__file__).resolve().parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    sys.modules.pop("src", None)
    app_module = importlib.import_module("src.app")


logger = app_module.logger
_startup = app_module._startup


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump(mode="json"))
    return str(value)


TOOL_DEFINITIONS = {
    "read_file": {
        "description": "Read and parse a supported document format.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "output_format": {"type": "string", "enum": ["json", "markdown", "text"]},
                "stream": {"type": "boolean"},
                "page_range": {
                    "type": ["array", "null"],
                    "items": {"type": "integer", "minimum": 1},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "include_images": {"type": "boolean"},
                "max_tokens_hint": {"type": "integer", "minimum": 1},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    "get_metadata": {
        "description": "Get document metadata without returning full content.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    "extract_table": {
        "description": "Extract a specific table from a document.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "table_index": {"type": "integer", "minimum": 1},
                "sheet_name": {"type": ["string", "null"]},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    "extract_images": {
        "description": "Extract images from a document.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "page_range": {
                    "type": ["array", "null"],
                    "items": {"type": "integer", "minimum": 1},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "max_dimension": {"type": ["integer", "null"], "minimum": 1},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    "search_file": {
        "description": "Search a parsed document for relevant passages.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1},
            },
            "required": ["path", "query"],
            "additionalProperties": False,
        },
    },
    "convert_to_markdown": {
        "description": "Convert a document to markdown output.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    "list_supported_formats": {
        "description": "List all supported input formats.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}


server = Server("parsival")


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(name=name, description=spec["description"], inputSchema=spec["inputSchema"])
        for name, spec in TOOL_DEFINITIONS.items()
    ]


@server.call_tool(validate_input=True)
async def _call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    tool_fn = app_module.TOOL_FUNCTIONS.get(name)
    if tool_fn is None:
        raise ValueError(f"Unknown tool: {name}")

    result = tool_fn(**(arguments or {}))
    if inspect.isawaitable(result):
        result = await result

    payload = _to_jsonable(result)
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, indent=2)

    return [types.TextContent(type="text", text=text)]


def _configure_stdio_safe_logging() -> None:
    """Ensure operational logs stay on stderr and never pollute MCP stdout frames."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
        return

    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setStream(sys.stderr)


async def _warmup() -> None:
    """Run shared startup init before serving stdio requests."""
    await _startup()


async def _serve_stdio() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    _configure_stdio_safe_logging()

    try:
        asyncio.run(_warmup())
    except Exception as exc:
        # Keep startup failure non-fatal to preserve current parse-time fallback behavior.
        logger.warning("stdio_startup_initialization_failed", error=str(exc))

    asyncio.run(_serve_stdio())


if __name__ == "__main__":
    main()
