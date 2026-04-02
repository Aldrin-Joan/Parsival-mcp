from src.tools.list_supported_formats import list_supported_formats_tool
from src.parsers.registry import list_supported_formats


def test_list_supported_formats_returns_all():
    result = list_supported_formats_tool()
    assert "server_version" in result
    assert isinstance(result["server_version"], str)

    expected = [fmt.value for fmt in list_supported_formats()]
    assert set(result["formats"]) == set(expected)
    assert result["count"] == len(expected)
