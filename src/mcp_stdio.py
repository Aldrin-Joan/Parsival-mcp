import asyncio
import importlib
import logging
import sys
from pathlib import Path

try:
    from src.app import mcp, _startup, logger
except ModuleNotFoundError:
    # Allow `python src/mcp_stdio.py` from repository root by adding parent to sys.path.
    project_root = str(Path(__file__).resolve().parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    sys.modules.pop("src", None)
    app_module = importlib.import_module("src.app")
    mcp = app_module.mcp
    _startup = app_module._startup
    logger = app_module.logger


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


def main() -> None:
    _configure_stdio_safe_logging()

    try:
        asyncio.run(_warmup())
    except Exception as exc:
        # Keep startup failure non-fatal to preserve current parse-time fallback behavior.
        logger.warning("stdio_startup_initialization_failed", error=str(exc))

    # FastMCP handles MCP protocol over stdin/stdout when transport='stdio'.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
