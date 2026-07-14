"""Initial schema for jobs, raw documents, and canonical threads."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.String(length=512), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])
    op.create_index("ix_ingestion_jobs_status_id", "ingestion_jobs", ["status", "id"])

    op.create_table(
        "canonical_threads",
        sa.Column("canonical_id", sa.String(length=64), nullable=False),
        sa.Column("message_ids", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("expected_parent_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("canonical_id"),
    )
    op.create_index(
        "ix_canonical_threads_expected_parent_id",
        "canonical_threads",
        ["expected_parent_id"],
    )

    op.create_table(
        "raw_documents",
        sa.Column("document_id", sa.String(length=512), nullable=False),
        sa.Column("canonical_id", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["canonical_id"], ["canonical_threads.canonical_id"]),
        sa.PrimaryKeyConstraint("document_id"),
    )
    op.create_index("ix_raw_documents_canonical_id", "raw_documents", ["canonical_id"])


def downgrade() -> None:
    op.drop_index("ix_raw_documents_canonical_id", table_name="raw_documents")
    op.drop_table("raw_documents")
    op.drop_index(
        "ix_canonical_threads_expected_parent_id",
        table_name="canonical_threads",
    )
    op.drop_table("canonical_threads")
    op.drop_index("ix_ingestion_jobs_status_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_document_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
