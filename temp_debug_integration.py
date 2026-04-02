from pathlib import Path
from src.tools.get_metadata import get_metadata
from src.core.router import FormatRouter
from src.parsers.registry import get_parser, _REGISTRY, register
from src.parsers.base import BaseParser
from src.models.enums import FileFormat

print('initial registry', list(_REGISTRY.keys()))

class TestParser(BaseParser):
    async def parse(self, path, options=None):
        raise NotImplementedError

    async def parse_metadata(self, path):
        raise NotImplementedError


@register(FileFormat.TEXT)
class RegisteredParser(TestParser):
    pass

print('after local register', list(_REGISTRY.keys()), _REGISTRY[FileFormat.TEXT])

p = Path('temp_sample.txt')
p.write_text('Hello world', encoding='utf-8')

fmt = FormatRouter().detect(str(p))
print('detected', fmt)
parser = get_parser(fmt)
print('parser from get_parser', type(parser), parser)

import asyncio
metadata = asyncio.run(get_metadata(str(p)))
print('metadata', metadata)

p.unlink()
