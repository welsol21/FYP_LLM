"""Universal book-extraction engine with pluggable format parsers."""

from .engine import (
    DEFAULT_GRAMMAR_ANCHORS,
    BookSnippet,
    BookTextPayload,
    UniversalBookExtractionEngine,
    load_cached_payload,
    save_payload_cache,
)
from .parsers import (
    DjvuBookParser,
    DocBookParser,
    DocxBookParser,
    EpubBookParser,
    OcrImageBookParser,
    PdfBookParser,
    PlainTextBookParser,
    ZipBookParser,
    build_default_parsers,
)

__all__ = [
    "DEFAULT_GRAMMAR_ANCHORS",
    "BookSnippet",
    "BookTextPayload",
    "DjvuBookParser",
    "DocBookParser",
    "DocxBookParser",
    "EpubBookParser",
    "OcrImageBookParser",
    "PlainTextBookParser",
    "PdfBookParser",
    "UniversalBookExtractionEngine",
    "ZipBookParser",
    "build_default_parsers",
    "load_cached_payload",
    "save_payload_cache",
]
