import importlib

import pytest

from src.parsers import registry as parser_registry


@pytest.fixture(autouse=True)
def parser_registry_isolation():
    # Preserve current parser registry state.
    original_registry = parser_registry._REGISTRY.copy()

    # Force reload parser modules and rebuild registry so tests are isolated.
    parser_registry._REGISTRY.clear()
    try:
        import src.parsers as parsers_pkg

        importlib.reload(parsers_pkg)
        for module_name in getattr(parsers_pkg, "__all__", []):
            if module_name in ("registry", "base"):
                continue
            full_name = f"src.parsers.{module_name}"
            try:
                module = importlib.import_module(full_name)
                importlib.reload(module)
            except ImportError:
                continue
    except ImportError:
        pass

    yield

    parser_registry._REGISTRY.clear()
    parser_registry._REGISTRY.update(original_registry)
