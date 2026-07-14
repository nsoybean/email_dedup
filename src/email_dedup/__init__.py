"""Email ingestion and canonical-thread construction."""

from email_dedup.canonicalization import assign_canonical, canonical_id_for
from email_dedup.models import CanonicalAssignment, ParsedMessage, ParsedThread, RawDocument
from email_dedup.parser import ParseError, parse_thread
from email_dedup.settings import Settings

__all__ = [
    "CanonicalAssignment",
    "ParseError",
    "ParsedMessage",
    "ParsedThread",
    "RawDocument",
    "Settings",
    "assign_canonical",
    "canonical_id_for",
    "parse_thread",
]
