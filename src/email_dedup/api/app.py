"""FastAPI application for document submission and assignment lookups."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from email_dedup.api.deps import get_db_session
from email_dedup.api.schemas import (
    CanonicalDocumentsResponse,
    CanonicalRelationsResponse,
    DocumentCanonicalResponse,
    DocumentSubmitRequest,
    DocumentSubmitResponse,
    ErrorResponse,
    HealthResponse,
    JobStatusResponse,
)
from email_dedup.db.repository import (
    DocumentConflictError,
    get_canonical_for_document,
    get_canonical_relations,
    get_documents_for_canonical,
    get_job,
    submit_document,
)
from email_dedup.db.session import create_db_engine, create_session_factory
from email_dedup.settings import Settings


def create_app(
    session_factory: sessionmaker[Session] | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Build the FastAPI app; tests may inject a session_factory."""
    resolved_settings = settings or Settings.from_environment()
    if session_factory is None:
        engine = create_db_engine(resolved_settings.database_url)
        session_factory = create_session_factory(engine)

    app = FastAPI(
        title="Email Dedup Ingestion API",
        description=(
            "Submit email thread snapshots for asynchronous ingestion and "
            "query document↔canonical mappings and one-hop hierarchy relations."
        ),
        version="0.1.0",
    )
    app.state.settings = resolved_settings
    app.state.session_factory = session_factory

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    def health(
        session: Annotated[Session, Depends(get_db_session)],
    ) -> HealthResponse:
        session.execute(text("SELECT 1"))
        return HealthResponse(status="ok", database="up")

    @app.post(
        "/documents",
        response_model=DocumentSubmitResponse,
        status_code=status.HTTP_202_ACCEPTED,
        responses={
            status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        },
        tags=["ingestion"],
        summary="Submit a document for asynchronous ingestion",
    )
    def post_document(
        body: DocumentSubmitRequest,
        session: Annotated[Session, Depends(get_db_session)],
    ) -> DocumentSubmitResponse:
        try:
            result = submit_document(session, body.document_id, body.content)
        except DocumentConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        return DocumentSubmitResponse(
            document_id=result.document_id,
            status=result.status,
            job_id=result.job_id,
            canonical_id=result.canonical_id,
        )

    @app.get(
        "/jobs/{job_id}",
        response_model=JobStatusResponse,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
        tags=["ingestion"],
        summary="Get ingestion job status",
    )
    def job_status(
        job_id: int,
        session: Annotated[Session, Depends(get_db_session)],
    ) -> JobStatusResponse:
        job = get_job(session, job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        return JobStatusResponse(
            job_id=job.id,
            document_id=job.document_id,
            status=job.status,
            attempts=job.attempts,
            error=job.error,
        )

    @app.get(
        "/documents/{doc_id}/canonical",
        response_model=DocumentCanonicalResponse,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
        tags=["lookups"],
        summary="Map a raw document to its canonical thread",
    )
    def document_canonical(
        doc_id: str,
        session: Annotated[Session, Depends(get_db_session)],
    ) -> DocumentCanonicalResponse:
        canonical_id = get_canonical_for_document(session, doc_id)
        if canonical_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="document not found",
            )
        return DocumentCanonicalResponse(document_id=doc_id, canonical_id=canonical_id)

    @app.get(
        "/canonicals/{canonical_id}/documents",
        response_model=CanonicalDocumentsResponse,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
        tags=["lookups"],
        summary="List raw documents for a canonical thread",
    )
    def canonical_documents(
        canonical_id: str,
        session: Annotated[Session, Depends(get_db_session)],
    ) -> CanonicalDocumentsResponse:
        document_ids = get_documents_for_canonical(session, canonical_id)
        if not document_ids:
            # Distinguish unknown canonical from empty (should not happen if FK holds)
            relations = get_canonical_relations(session, canonical_id)
            if relations is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="canonical not found",
                )
        return CanonicalDocumentsResponse(
            canonical_id=canonical_id,
            document_ids=document_ids,
        )

    @app.get(
        "/canonicals/{canonical_id}/relations",
        response_model=CanonicalRelationsResponse,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
        tags=["lookups"],
        summary="Direct parent and children for a canonical thread",
    )
    def canonical_relations(
        canonical_id: str,
        session: Annotated[Session, Depends(get_db_session)],
    ) -> CanonicalRelationsResponse:
        relations = get_canonical_relations(session, canonical_id)
        if relations is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="canonical not found",
            )
        return CanonicalRelationsResponse(
            canonical_id=relations.canonical_id,
            parent_id=relations.parent_id,
            child_ids=list(relations.child_ids),
        )

    return app


app = create_app()
