from src.parsers.base import BaseParser


class DummyParser(BaseParser):
    async def parse(self, path, options=None):
        raise NotImplementedError

    async def parse_metadata(self, path):
        raise NotImplementedError


def test_base_parser_stream_sections_not_implemented():
    dp = DummyParser()
    assert not dp.supports_streaming()
