"""Persistence operations for ingestion jobs and canonical threads."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from email_dedup.db.models import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_PROCESSING,
    CanonicalThread,
    IngestionJob,
    RawDocument,
)
from email_dedup.hierarchy import assign_with_parent
from email_dedup.parser import parse_thread


class DocumentConflictError(ValueError):
    """Raised when the same document_id is submitted with different content."""


@dataclass(frozen=True, slots=True)
class CanonicalRelations:
    canonical_id: str
    parent_id: str | None
    child_ids: tuple[str, ...]


def content_hash_for(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def enqueue_job(session: Session, document_id: str, payload: str) -> IngestionJob:
    """Insert a pending job carrying the full document payload."""
    job = IngestionJob(
        document_id=document_id,
        payload=payload,
        content_hash=content_hash_for(payload),
        status=JOB_STATUS_PENDING,
    )
    session.add(job)
    session.flush()
    return job


def claim_next_job(session: Session) -> IngestionJob | None:
    """Claim one pending job using SKIP LOCKED for concurrent workers."""
    stmt = (
        select(IngestionJob)
        .where(IngestionJob.status == JOB_STATUS_PENDING)
        .order_by(IngestionJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = session.scalars(stmt).first()
    if job is None:
        return None
    job.status = JOB_STATUS_PROCESSING
    job.attempts += 1
    session.flush()
    return job


def complete_job(session: Session, job_id: int) -> None:
    session.execute(
        update(IngestionJob)
        .where(IngestionJob.id == job_id)
        .values(status=JOB_STATUS_COMPLETED, error=None)
    )


def fail_job(session: Session, job_id: int, error: str) -> None:
    session.execute(
        update(IngestionJob)
        .where(IngestionJob.id == job_id)
        .values(status=JOB_STATUS_FAILED, error=error)
    )


def upsert_processed_document(
    session: Session,
    document_id: str,
    payload: str,
) -> str:
    """Parse payload and upsert canonical + raw document mapping.

    Returns the canonical_id. Raises DocumentConflictError on content mismatch.
    """
    content_hash = content_hash_for(payload)
    existing = session.get(RawDocument, document_id)
    if existing is not None and existing.content_hash != content_hash:
        raise DocumentConflictError(
            f"document_id {document_id!r} already exists with different content"
        )

    thread = parse_thread(payload)
    assignment = assign_with_parent(document_id, thread.message_ids)

    session.execute(
        insert(CanonicalThread)
        .values(
            canonical_id=assignment.canonical_id,
            message_ids=list(assignment.message_ids),
            expected_parent_id=assignment.expected_parent_id,
        )
        .on_conflict_do_nothing(index_elements=[CanonicalThread.canonical_id])
    )

    if existing is None:
        session.add(
            RawDocument(
                document_id=document_id,
                canonical_id=assignment.canonical_id,
                content_hash=content_hash,
            )
        )
    session.flush()
    return assignment.canonical_id


def process_job(session: Session, job: IngestionJob) -> str:
    """Process a claimed job. Caller owns commit/rollback."""
    canonical_id = upsert_processed_document(session, job.document_id, job.payload)
    complete_job(session, job.id)
    return canonical_id


def get_canonical_for_document(session: Session, document_id: str) -> str | None:
    row = session.get(RawDocument, document_id)
    return None if row is None else row.canonical_id


def get_documents_for_canonical(session: Session, canonical_id: str) -> list[str]:
    rows = session.scalars(
        select(RawDocument.document_id)
        .where(RawDocument.canonical_id == canonical_id)
        .order_by(RawDocument.document_id)
    ).all()
    return list(rows)


def get_canonical_relations(session: Session, canonical_id: str) -> CanonicalRelations | None:
    node = session.get(CanonicalThread, canonical_id)
    if node is None:
        return None

    parent_id = None
    if node.expected_parent_id is not None:
        parent = session.get(CanonicalThread, node.expected_parent_id)
        if parent is not None:
            parent_id = parent.canonical_id

    child_ids = session.scalars(
        select(CanonicalThread.canonical_id)
        .where(CanonicalThread.expected_parent_id == canonical_id)
        .order_by(CanonicalThread.canonical_id)
    ).all()
    return CanonicalRelations(
        canonical_id=canonical_id,
        parent_id=parent_id,
        child_ids=tuple(child_ids),
    )
