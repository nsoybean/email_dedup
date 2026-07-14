"""Database package exports."""

from email_dedup.db.base import Base
from email_dedup.db.models import CanonicalThread, IngestionJob, RawDocument
from email_dedup.db.repository import (
    CanonicalRelations,
    DocumentConflictError,
    claim_next_job,
    enqueue_job,
    get_canonical_for_document,
    get_canonical_relations,
    get_documents_for_canonical,
    process_job,
    upsert_processed_document,
)
from email_dedup.db.session import create_db_engine, create_session_factory, session_scope

__all__ = [
    "Base",
    "CanonicalRelations",
    "CanonicalThread",
    "DocumentConflictError",
    "IngestionJob",
    "RawDocument",
    "claim_next_job",
    "create_db_engine",
    "create_session_factory",
    "enqueue_job",
    "get_canonical_for_document",
    "get_canonical_relations",
    "get_documents_for_canonical",
    "process_job",
    "session_scope",
    "upsert_processed_document",
]
