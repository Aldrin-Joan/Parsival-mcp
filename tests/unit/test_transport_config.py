import pytest

from src.config import Settings
from src.mcp_entrypoint import _validate_fastmcp_network_config


def test_transport_default_is_fastmcp(monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    cfg = Settings()
    assert cfg.TRANSPORT == "fastmcp"
    assert cfg.is_stdio_transport is False


def test_transport_accepts_stdio_case_insensitive():
    cfg = Settings(TRANSPORT="STDIO")
    assert cfg.TRANSPORT == "stdio"
    assert cfg.is_stdio_transport is True


def test_transport_rejects_invalid_value():
    with pytest.raises(ValueError, match="TRANSPORT must be one of"):
        Settings(TRANSPORT="http")


def test_validate_fastmcp_network_config_requires_host(monkeypatch):
    monkeypatch.delenv("FASTMCP_SERVER_HOST", raising=False)
    monkeypatch.setenv("FASTMCP_SERVER_PORT", "8000")

    with pytest.raises(ValueError, match="FASTMCP_SERVER_HOST is required"):
        _validate_fastmcp_network_config()


def test_validate_fastmcp_network_config_requires_port(monkeypatch):
    monkeypatch.setenv("FASTMCP_SERVER_HOST", "0.0.0.0")
    monkeypatch.delenv("FASTMCP_SERVER_PORT", raising=False)

    with pytest.raises(ValueError, match="FASTMCP_SERVER_PORT is required"):
        _validate_fastmcp_network_config()


def test_validate_fastmcp_network_config_rejects_non_integer_port(monkeypatch):
    monkeypatch.setenv("FASTMCP_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("FASTMCP_SERVER_PORT", "abc")

    with pytest.raises(ValueError, match="must be an integer"):
        _validate_fastmcp_network_config()


def test_validate_fastmcp_network_config_rejects_out_of_range_port(monkeypatch):
    monkeypatch.setenv("FASTMCP_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("FASTMCP_SERVER_PORT", "70000")

    with pytest.raises(ValueError, match="must be in range"):
        _validate_fastmcp_network_config()


def test_validate_fastmcp_network_config_accepts_valid_values(monkeypatch):
    monkeypatch.setenv("FASTMCP_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("FASTMCP_SERVER_PORT", "8000")

    host, port = _validate_fastmcp_network_config()
    assert host == "0.0.0.0"
    assert port == 8000
