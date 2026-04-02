import os

from src.app import mcp, logger
from src.config import settings
from src.mcp_stdio import main as run_stdio_main


def _validate_fastmcp_network_config() -> tuple[str, int]:
    host = os.getenv("FASTMCP_SERVER_HOST")
    port_text = os.getenv("FASTMCP_SERVER_PORT")

    if not host:
        raise ValueError("FASTMCP_SERVER_HOST is required when MCP_TRANSPORT=fastmcp")
    if not port_text:
        raise ValueError("FASTMCP_SERVER_PORT is required when MCP_TRANSPORT=fastmcp")

    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError("FASTMCP_SERVER_PORT must be an integer when MCP_TRANSPORT=fastmcp") from exc

    if port < 1 or port > 65535:
        raise ValueError("FASTMCP_SERVER_PORT must be in range 1..65535 when MCP_TRANSPORT=fastmcp")

    return host, port


def main() -> None:
    transport = settings.TRANSPORT

    if transport == "stdio":
        # Stdio mode does not require network host/port values.
        if os.getenv("FASTMCP_SERVER_HOST") or os.getenv("FASTMCP_SERVER_PORT"):
            logger.info("stdio_ignoring_fastmcp_network_env")
        run_stdio_main()
        return

    if transport == "fastmcp":
        host, port = _validate_fastmcp_network_config()
        logger.info("fastmcp_sse_start", host=host, port=port)
        mcp.run(transport="sse")
        return

    raise ValueError(f"Unsupported MCP_TRANSPORT value: {transport}")


if __name__ == "__main__":
    main()
