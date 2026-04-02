from __future__ import annotations
import importlib.metadata
from src.models.enums import FileFormat
from src.parsers.registry import register
from src.core.logging import get_logger

logger = get_logger(__name__)


def load_plugins() -> None:
    """Loads external parser plugins via entry points."""
    try:
        entry_points = importlib.metadata.entry_points()
        parser_eps = (
            entry_points.select(group="parsival.parsers")
            if hasattr(entry_points, "select")
            else entry_points.get("parsival.parsers", [])
        )
        for ep in parser_eps:
            try:
                parser_cls = ep.load()
                fmt_name = ep.name.lower()
                if fmt_name not in {f.value for f in FileFormat}:
                    continue

                fmt = FileFormat(fmt_name)
                register(fmt)(parser_cls)
                logger.info("plugin_registered", plugin=ep.name, format=fmt)
            except Exception as e:
                logger.warning("plugin_load_failed", plugin_getattr=str(ep), error=str(e))
    except Exception as e:
        logger.debug("plugin_loader_disabled", error=str(e))
