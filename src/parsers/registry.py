from __future__ import annotations
from typing import Type
from src.models.enums import FileFormat
from src.parsers.base import BaseParser

_REGISTRY: dict[FileFormat, BaseParser] = {}


def _ensure_parsers_loaded() -> None:
    """Ensure parser modules are imported so registration happens."""
    try:
        import src.parsers  # noqa: F401
    except ImportError:
        # If src.parsers is not importable, we can't auto-load parsers,
        # but we continue so calling code can raise appropriate errors.
        pass


def register(fmt: FileFormat):
    def decorator(cls: Type[BaseParser]) -> Type[BaseParser]:
        instance = cls()
        _REGISTRY[fmt] = instance
        return cls

    return decorator


def get_parser(fmt: FileFormat) -> BaseParser:
    _ensure_parsers_loaded()
    parser = _REGISTRY.get(fmt)

    if parser is None:
        raise ValueError(f"No parser registered for format: {fmt}")
    return parser


def list_supported_formats() -> list[FileFormat]:
    _ensure_parsers_loaded()
    return list(_REGISTRY.keys())


def reset_registry() -> None:
    """Reset the parser registry. For tests and external integration paths."""
    _REGISTRY.clear()
