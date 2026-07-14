"""Pydantic request and response models for the ingestion API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentSubmitRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1)


class DocumentSubmitResponse(BaseModel):
    document_id: str
    status: str
    job_id: int | None = None
    canonical_id: str | None = None


class JobStatusResponse(BaseModel):
    job_id: int
    document_id: str
    status: str
    attempts: int
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    database: str


class DocumentCanonicalResponse(BaseModel):
    document_id: str
    canonical_id: str


class CanonicalDocumentsResponse(BaseModel):
    canonical_id: str
    document_ids: list[str]


class CanonicalRelationsResponse(BaseModel):
    canonical_id: str
    parent_id: str | None
    child_ids: list[str]


class ErrorResponse(BaseModel):
    detail: str
