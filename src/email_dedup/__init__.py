"""Email ingestion and canonical-thread construction."""

from email_dedup.models import RawDocument
from email_dedup.settings import Settings

__all__ = ["RawDocument", "Settings"]
