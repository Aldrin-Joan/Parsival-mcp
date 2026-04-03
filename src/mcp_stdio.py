import asyncio
import importlib
import inspect
import json
import logging
import sys
import time
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


def _to_content_string(value: Any) -> str:
    jsonable = _to_jsonable(value)
    if isinstance(jsonable, str):
        return jsonable
    return json.dumps(jsonable, sort_keys=True)


def _base_response(status: str, content: str, error: str | None, confidence: float) -> dict[str, Any]:
    return {
        "status": status,
        "content": content,
        "error": error,
        "confidence": max(0.0, min(1.0, float(confidence))),
    }


def _build_tool_response(name: str, raw_result: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    jsonable = _to_jsonable(raw_result)

    if name == "read_file" and isinstance(jsonable, dict):
        parse_status = str(jsonable.get("status", "")).lower()
        content = (jsonable.get("content") or "")
        errors = jsonable.get("errors") or []
        error_message = ""
        if errors and isinstance(errors, list):
            first = errors[0]
            if isinstance(first, dict):
                error_message = str(first.get("message") or first.get("code") or "")
            else:
                error_message = str(first)

        if parse_status == "unsupported":
            return _base_response("unsupported", content or "Unsupported file format", error_message or "unsupported_format", 0.0)
        if parse_status in {"failed", "oversize"}:
            return _base_response("error", content or "", error_message or parse_status, 0.0)
        if not str(content).strip():
            return _base_response("error", "", "empty_content", 0.0)

        conf = 0.95 if parse_status == "ok" else 0.7
        conf = min(1.0, max(0.5, conf + min(len(str(content)) / 5000.0, 0.25)))
        return _base_response("success", str(content), None, conf)

    if name == "convert_to_markdown":
        content = _to_content_string(jsonable).strip()
        if not content:
            return _base_response("error", "", "empty_content", 0.0)
        return _base_response("success", content, None, min(1.0, 0.7 + min(len(content) / 5000.0, 0.3)))

    if name == "extract_table" and isinstance(jsonable, dict):
        row_count = int(jsonable.get("row_count") or 0)
        markdown = str(jsonable.get("markdown") or "")
        if row_count < 2:
            return _base_response("error", "", "no_table_found", 0.0)
        content = markdown.strip() or _to_content_string(jsonable)
        return _base_response("success", content, None, 0.85)

    if name == "search_file" and isinstance(jsonable, list):
        if not jsonable:
            return _base_response("error", "", "no_results", 0.0)

        query = str(arguments.get("query") or "").lower().strip()
        confidences = []
        for hit in jsonable:
            if isinstance(hit, dict):
                conf = float(hit.get("confidence") or 0.0)
                snippet = str(hit.get("snippet") or "").lower()
                if query and query not in snippet:
                    conf = max(0.0, conf - 0.5)
                confidences.append(conf)

        overall = sum(confidences) / len(confidences) if confidences else 0.0
        return _base_response("success", _to_content_string(jsonable), None, overall)

    content = _to_content_string(jsonable)
    if not content.strip():
        return _base_response("error", "", "empty_content", 0.0)
    return _base_response("success", content, None, min(1.0, 0.6 + min(len(content) / 10000.0, 0.4)))


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
    start = time.perf_counter()
    file_arg = str((arguments or {}).get("path") or (arguments or {}).get("file") or "")

    tool_fn = app_module.TOOL_FUNCTIONS.get(name)
    if tool_fn is None:
        payload = _base_response("error", "", f"Unknown tool: {name}", 0.0)
        text = json.dumps(payload, indent=2, sort_keys=True)
        logger.info(
            "tool_call",
            tool=name,
            file=file_arg,
            status="error",
            error_type="unknown_tool",
            latency_ms=(time.perf_counter() - start) * 1000,
        )
        return [types.TextContent(type="text", text=text)]

    try:
        result = tool_fn(**(arguments or {}))
        if inspect.isawaitable(result):
            result = await result

        payload = _build_tool_response(name, result, arguments or {})
        text = json.dumps(payload, indent=2, sort_keys=True)
        logger.info(
            "tool_call",
            tool=name,
            file=file_arg,
            status=payload.get("status"),
            error_type=payload.get("error") or "",
            latency_ms=(time.perf_counter() - start) * 1000,
        )
    except Exception as exc:
        payload = _base_response("error", "", str(exc), 0.0)
        text = json.dumps(payload, indent=2, sort_keys=True)
        logger.warning(
            "tool_call",
            tool=name,
            file=file_arg,
            status="error",
            error_type=type(exc).__name__,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

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
