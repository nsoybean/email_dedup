"""ORM models for jobs, raw documents, and canonical threads."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from email_dedup.db.base import Base

JOB_STATUS_PENDING = "pending"
JOB_STATUS_PROCESSING = "processing"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (Index("ix_ingestion_jobs_status_id", "status", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JOB_STATUS_PENDING)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CanonicalThread(Base):
    __tablename__ = "canonical_threads"
    __table_args__ = (Index("ix_canonical_threads_expected_parent_id", "expected_parent_id"),)

    canonical_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    message_ids: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    expected_parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    documents: Mapped[list[RawDocument]] = relationship(back_populates="canonical")


class RawDocument(Base):
    __tablename__ = "raw_documents"

    document_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    canonical_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("canonical_threads.canonical_id"),
        nullable=False,
        index=True,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    canonical: Mapped[CanonicalThread] = relationship(back_populates="documents")
