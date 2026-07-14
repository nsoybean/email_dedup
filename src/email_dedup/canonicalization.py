"""Deterministic canonical IDs from ordered Message-ID sequences."""

from __future__ import annotations

import hashlib

from email_dedup.models import CanonicalAssignment


def encode_message_ids(message_ids: tuple[str, ...] | list[str]) -> str:
    """Stable encoding used as the hash input for a canonical thread."""
    if not message_ids:
        raise ValueError("message_ids must not be empty")
    if any(not message_id.strip() for message_id in message_ids):
        raise ValueError("message_ids must not contain blank values")
    return "\n".join(message_ids)


def canonical_id_for(message_ids: tuple[str, ...] | list[str]) -> str:
    """Return SHA-256 hex digest of the newest-first Message-ID sequence."""
    encoded = encode_message_ids(message_ids)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def assign_canonical(
    document_id: str,
    message_ids: tuple[str, ...] | list[str],
) -> CanonicalAssignment:
    """Map one raw document to its deterministic canonical thread id."""
    if not document_id.strip():
        raise ValueError("document_id must not be blank")
    ids = tuple(message_ids)
    return CanonicalAssignment(
        document_id=document_id,
        canonical_id=canonical_id_for(ids),
        message_ids=ids,
    )
