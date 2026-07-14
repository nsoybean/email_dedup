from __future__ import annotations

import threading

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from email_dedup.db.models import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_PENDING,
    IngestionJob,
)
from email_dedup.db.repository import (
    DocumentConflictError,
    claim_next_job,
    enqueue_job,
    get_canonical_for_document,
    get_canonical_relations,
    get_documents_for_canonical,
    process_job,
    upsert_processed_document,
)
from email_dedup.db.session import create_session_factory
from tests.integration.conftest import read_eval

pytestmark = pytest.mark.integration


def test_enqueue_claim_and_process(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        job = enqueue_job(session, "1_0_0.txt", read_eval("1_0_0.txt"))
        session.commit()
        job_id = job.id

    with session_factory() as session:
        claimed = claim_next_job(session)
        assert claimed is not None
        assert claimed.id == job_id
        canonical_id = process_job(session, claimed)
        session.commit()

    with session_factory() as session:
        assert get_canonical_for_document(session, "1_0_0.txt") == canonical_id
        assert get_documents_for_canonical(session, canonical_id) == ["1_0_0.txt"]
        row = session.get(IngestionJob, job_id)
        assert row is not None
        assert row.status == JOB_STATUS_COMPLETED


def test_idempotent_same_content_and_conflict(
    session_factory: sessionmaker[Session],
) -> None:
    payload = read_eval("1.txt")
    with session_factory() as session:
        first = upsert_processed_document(session, "1.txt", payload)
        second = upsert_processed_document(session, "1.txt", payload)
        assert first == second
        session.commit()

    with session_factory() as session:
        with pytest.raises(DocumentConflictError):
            upsert_processed_document(session, "1.txt", read_eval("1_0.txt"))


def test_child_first_parent_resolves_on_query(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        child_id = upsert_processed_document(session, "1_0_0.txt", read_eval("1_0_0.txt"))
        relations = get_canonical_relations(session, child_id)
        assert relations is not None
        assert relations.parent_id is None
        session.commit()

    with session_factory() as session:
        parent_id = upsert_processed_document(session, "1_0.txt", read_eval("1_0.txt"))
        relations = get_canonical_relations(session, child_id)
        assert relations is not None
        assert relations.parent_id == parent_id
        parent_relations = get_canonical_relations(session, parent_id)
        assert parent_relations is not None
        assert child_id in parent_relations.child_ids
        session.commit()


def test_variants_share_canonical(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        a = upsert_processed_document(session, "1_0_0.txt", read_eval("1_0_0.txt"))
        b = upsert_processed_document(session, "1_0_0b.txt", read_eval("1_0_0b.txt"))
        assert a == b
        assert get_documents_for_canonical(session, a) == ["1_0_0.txt", "1_0_0b.txt"]
        session.commit()


def test_concurrent_claims_are_unique(
    session_factory: sessionmaker[Session],
    migrated_engine: Engine,
) -> None:
    with session_factory() as session:
        for index in range(10):
            enqueue_job(session, f"doc{index}.txt", read_eval("1.txt"))
        session.commit()

    claimed_ids: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        local_factory = create_session_factory(migrated_engine)
        while True:
            with local_factory() as session:
                job = claim_next_job(session)
                if job is None:
                    session.commit()
                    return
                with lock:
                    claimed_ids.append(job.id)
                job.status = JOB_STATUS_COMPLETED
                session.commit()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(claimed_ids) == 10
    assert len(set(claimed_ids)) == 10

    with session_factory() as session:
        pending = session.scalars(
            select(IngestionJob).where(IngestionJob.status == JOB_STATUS_PENDING)
        ).all()
        assert pending == []
