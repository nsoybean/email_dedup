"""Email ingestion and canonical-thread construction."""

from email_dedup.models import ParsedMessage, ParsedThread, RawDocument
from email_dedup.parser import ParseError, parse_thread
from email_dedup.settings import Settings

__all__ = [
    "ParseError",
    "ParsedMessage",
    "ParsedThread",
    "RawDocument",
    "Settings",
    "parse_thread",
]
