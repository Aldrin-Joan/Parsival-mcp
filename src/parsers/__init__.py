from . import (
    base,
    registry,
    pdf_parser,
    docx_parser,
    xlsx_parser,
    csv_parser,
    doc_parser,
    pptx_parser,
    html_parser,
    text_parser,
)
from .plugin_loader import load_plugins

# Load external parser plugins from installed packages.
load_plugins()

__all__ = [
    "base",
    "registry",
    "pdf_parser",
    "docx_parser",
    "xlsx_parser",
    "csv_parser",
    "doc_parser",
    "pptx_parser",
    "html_parser",
    "text_parser",
]
