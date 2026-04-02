import pytest

from src.config import Settings


def test_transport_default_is_stdio(monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    cfg = Settings()
    assert cfg.TRANSPORT == "stdio"
    assert cfg.is_stdio_transport is True


def test_transport_accepts_stdio_case_insensitive():
    cfg = Settings(TRANSPORT="STDIO")
    assert cfg.TRANSPORT == "stdio"
    assert cfg.is_stdio_transport is True


def test_transport_rejects_invalid_value():
    with pytest.raises(ValueError, match="TRANSPORT must be"):
        Settings(TRANSPORT="http")
