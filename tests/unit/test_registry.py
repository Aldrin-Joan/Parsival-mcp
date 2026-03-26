from src.parsers.registry import register, get_parser, list_supported_formats
from src.parsers.base import BaseParser
from src.models.enums import FileFormat


class TestParser(BaseParser):
    async def parse(self, path, options=None):
        raise NotImplementedError

    async def parse_metadata(self, path):
        raise NotImplementedError


@register(FileFormat.TEXT)
class RegisteredParser(TestParser):
    pass


def test_registry_get_parser():
    parser = get_parser(FileFormat.TEXT)
    assert parser is not None


def test_list_supported_formats():
    fmts = list_supported_formats()
    assert FileFormat.TEXT in fmts
