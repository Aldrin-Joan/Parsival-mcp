from src.models.enums import FileFormat, OutputFormat, ParseStatus, SectionType


def test_enums_values():
    assert FileFormat.PDF == "pdf"
    assert OutputFormat.JSON == "json"
    assert ParseStatus.OK == "ok"
    assert SectionType.LIST == "list"
