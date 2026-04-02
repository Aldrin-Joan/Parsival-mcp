"""Compatibility shim for PyMuPDF `fitz` module.

This directory is on sys.path before site-packages, so importing fitz will map to
pymupdf (PyMuPDF) even if another non-PyMuPDF fitz package is installed.
"""

import importlib

try:
    _pymupdf = importlib.import_module("pymupdf")
    if not hasattr(_pymupdf, "open"):
        raise ImportError("pymupdf module does not expose open()")

    # bring all public attributes into this module namespace
    for _name in dir(_pymupdf):
        if not _name.startswith("__"):
            globals()[_name] = getattr(_pymupdf, _name)

except Exception as exc:
    raise ImportError("Failed to load pymupdf as fitz: %s" % exc)
