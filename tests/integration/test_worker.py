"""Worker loop integration: retries, permanent failures, concurrent drain."""

from __future__ import annotations

import random
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from email_dedup.db.models import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    IngestionJob,
    RawDocument,
)
from email_dedup.db.repository import enqueue_job
from email_dedup.db.session import create_session_factory
from email_dedup.worker import process_next_job, run_worker_loop
from tests.integration.conftest import EVAL_DIR, read_eval

pytestmark = pytest.mark.integration


def _enqueue_eval_subset(
    session_factory: sessionmaker[Session],
    names: list[str],
) -> None:
    with session_factory() as session:
        for name in names:
            enqueue_job(session, name, read_eval(name))
        session.commit()


def _count_by_status(session_factory: sessionmaker[Session], status: str) -> int:
    with session_factory() as session:
        return int(
            session.scalar(
                select(func.count()).select_from(IngestionJob).where(IngestionJob.status == status)
            )
            or 0
        )


def _wait_until_idle(session_factory: sessionmaker[Session], *, expected: int) -> None:
    for _ in range(200):
        pending = _count_by_status(session_factory, JOB_STATUS_PENDING)
        processing = _count_by_status(session_factory, "processing")
        done = _count_by_status(session_factory, JOB_STATUS_COMPLETED) + _count_by_status(
            session_factory, JOB_STATUS_FAILED
        )
        if pending == 0 and processing == 0 and done >= expected:
            return
        threading.Event().wait(0.05)
    pytest.fail("workers did not drain the queue in time")


def test_permanent_parse_failure_marks_failed(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        enqueue_job(session, "bad.txt", "not a real email thread")
        session.commit()

    outcome = process_next_job(session_factory, max_attempts=3)
    assert outcome.status == "failed"
    assert _count_by_status(session_factory, JOB_STATUS_FAILED) == 1
    assert _count_by_status(session_factory, JOB_STATUS_PENDING) == 0


def test_transient_failure_requeues_then_succeeds(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        enqueue_job(session, "1.txt", read_eval("1.txt"))
        session.commit()

    calls = {"n": 0}
    real_process = __import__(
        "email_dedup.db.repository", fromlist=["process_job"]
    ).process_job

    def flaky_process(session: Session, job: IngestionJob) -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError(f"transient boom #{calls['n']}")
        return real_process(session, job)

    with patch("email_dedup.worker.process_job", side_effect=flaky_process):
        assert process_next_job(session_factory, max_attempts=3).status == "requeued"
        assert process_next_job(session_factory, max_attempts=3).status == "requeued"
        assert process_next_job(session_factory, max_attempts=3).status == "completed"

    assert _count_by_status(session_factory, JOB_STATUS_COMPLETED) == 1
    with session_factory() as session:
        assert session.get(RawDocument, "1.txt") is not None


def test_exhausted_retries_mark_failed(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        enqueue_job(session, "1.txt", read_eval("1.txt"))
        session.commit()

    with patch(
        "email_dedup.worker.process_job",
        side_effect=RuntimeError("always broken"),
    ):
        assert process_next_job(session_factory, max_attempts=2).status == "requeued"
        assert process_next_job(session_factory, max_attempts=2).status == "failed"

    assert _count_by_status(session_factory, JOB_STATUS_FAILED) == 1
    assert _count_by_status(session_factory, JOB_STATUS_PENDING) == 0


def test_three_workers_drain_randomized_eval_subset(
    session_factory: sessionmaker[Session],
    migrated_engine,
) -> None:
    names = sorted(p.name for p in EVAL_DIR.glob("*.txt"))
    random.Random(42).shuffle(names)
    subset = names[:40]
    _enqueue_eval_subset(session_factory, subset)

    stop = threading.Event()
    errors: list[BaseException] = []

    def worker() -> None:
        local = create_session_factory(migrated_engine)
        try:
            run_worker_loop(
                local,
                max_attempts=3,
                poll_interval_seconds=0.05,
                stop_event=stop,
            )
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, name=f"w{i}") for i in range(3)]
    for thread in threads:
        thread.start()

    try:
        _wait_until_idle(session_factory, expected=len(subset))
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=5)

    assert errors == []
    assert _count_by_status(session_factory, JOB_STATUS_COMPLETED) == len(subset)
    assert _count_by_status(session_factory, JOB_STATUS_FAILED) == 0

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(RawDocument)) == len(subset)

    # Resubmit: workers complete again; raw_documents stays one row per document_id.
    _enqueue_eval_subset(session_factory, subset)
    stop2 = threading.Event()
    threads2 = [
        threading.Thread(
            target=lambda: run_worker_loop(
                create_session_factory(migrated_engine),
                max_attempts=3,
                poll_interval_seconds=0.05,
                stop_event=stop2,
            )
        )
        for _ in range(3)
    ]
    for thread in threads2:
        thread.start()
    try:
        _wait_until_idle(session_factory, expected=len(subset) * 2)
    finally:
        stop2.set()
        for thread in threads2:
            thread.join(timeout=5)

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(RawDocument)) == len(subset)
