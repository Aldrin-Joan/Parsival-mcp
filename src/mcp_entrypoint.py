from src.app import logger
from src.config import settings
from src.mcp_stdio import main as run_stdio_main


def main() -> None:
    transport = settings.TRANSPORT

    if transport != "stdio":
        raise ValueError(f"Unsupported MCP_TRANSPORT value: {transport}. Only 'stdio' is supported.")

    logger.info("stdio_server_start")
    run_stdio_main()


if __name__ == "__main__":
    main()
