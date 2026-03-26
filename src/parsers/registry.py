from __future__ import annotations
from typing import Type
from src.models.enums import FileFormat
from src.parsers.base import BaseParser

_REGISTRY: dict[FileFormat, BaseParser] = {}


def register(fmt: FileFormat):
    def decorator(cls: Type[BaseParser]) -> Type[BaseParser]:
        instance = cls()
        _REGISTRY[fmt] = instance
        return cls
    return decorator


def get_parser(fmt: FileFormat) -> BaseParser:
    parser = _REGISTRY.get(fmt)
    if parser is None:
        raise ValueError(f"No parser registered for format: {fmt}")
    return parser


def list_supported_formats() -> list[FileFormat]:
    return list(_REGISTRY.keys())
