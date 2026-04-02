from src.models.enums import FileFormat
from src.parsers.registry import get_parser, _REGISTRY
print('before', list(_REGISTRY.keys()))
parser = get_parser(FileFormat.TEXT)
print('parser', type(parser), parser)
print('after', list(_REGISTRY.keys()))
import src.parsers
print('after import src.parsers', list(_REGISTRY.keys()))
parser2 = get_parser(FileFormat.TEXT)
print('parser2', type(parser2), parser2)
