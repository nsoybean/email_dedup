"""Ingestion worker: claim jobs, process, retry, and shut down cleanly."""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from email_dedup.db.models import IngestionJob
from email_dedup.db.repository import (
    DocumentConflictError,
    claim_next_job,
    fail_job,
    process_job,
    requeue_job,
)
from email_dedup.db.session import create_db_engine, create_session_factory
from email_dedup.parser import ParseError
from email_dedup.settings import Settings

logger = logging.getLogger(__name__)

# Permanent failures should not burn retry budget — record and move on.
_PERMANENT_ERRORS: tuple[type[BaseException], ...] = (DocumentConflictError, ParseError)


@dataclass(frozen=True, slots=True)
class ProcessOutcome:
    """Result of one claim attempt: idle or a handled job."""

    claimed: bool
    status: str  # idle | completed | requeued | failed


def is_permanent_error(exc: BaseException) -> bool:
    return isinstance(exc, _PERMANENT_ERRORS)


def process_next_job(
    session_factory: sessionmaker[Session],
    *,
    max_attempts: int,
) -> ProcessOutcome:
    """Claim at most one job and process it transactionally.

    The claim is committed first so attempt counts survive a later rollback.
    On success the job is completed. On failure it is requeued (attempts left)
    or marked failed (permanent error or retry budget exhausted).
    """
    with session_factory() as session:
        job = claim_next_job(session)
        if job is None:
            session.commit()
            return ProcessOutcome(claimed=False, status="idle")
        job_id = job.id
        attempts = job.attempts
        session.commit()

    with session_factory() as session:
        try:
            # Re-load the claimed row for this transaction (status already processing).
            claimed = session.get(IngestionJob, job_id)
            if claimed is None:  # pragma: no cover - defensive
                return ProcessOutcome(claimed=True, status="failed")
            process_job(session, claimed)
            session.commit()
            logger.info("job %s completed (attempt %s)", job_id, attempts)
            return ProcessOutcome(claimed=True, status="completed")
        except Exception as exc:
            session.rollback()
            error_text = str(exc)[:2000]
            permanent = is_permanent_error(exc)
            with session_factory() as recovery:
                if permanent or attempts >= max_attempts:
                    fail_job(recovery, job_id, error_text)
                    recovery.commit()
                    logger.warning(
                        "job %s failed permanently (attempt %s): %s",
                        job_id,
                        attempts,
                        error_text,
                    )
                    return ProcessOutcome(claimed=True, status="failed")
                requeue_job(recovery, job_id, error_text)
                recovery.commit()
                logger.warning(
                    "job %s requeued (attempt %s/%s): %s",
                    job_id,
                    attempts,
                    max_attempts,
                    error_text,
                )
                return ProcessOutcome(claimed=True, status="requeued")


def run_worker_loop(
    session_factory: sessionmaker[Session],
    *,
    max_attempts: int,
    poll_interval_seconds: float,
    stop_event: threading.Event,
    idle_callback: Callable[[], None] | None = None,
) -> None:
    """Poll until ``stop_event`` is set. Sleeps only when the queue is idle."""
    while not stop_event.is_set():
        outcome = process_next_job(session_factory, max_attempts=max_attempts)
        if outcome.claimed:
            continue
        if idle_callback is not None:
            idle_callback()
        stop_event.wait(timeout=poll_interval_seconds)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [worker] %(message)s",
    )
    settings = Settings.from_environment()
    logging.getLogger().setLevel(settings.log_level)

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    stop_event = threading.Event()

    def _request_stop(signum: int, _frame: object) -> None:
        logger.info("received signal %s; shutting down after current job", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    logger.info(
        "starting worker poll=%.2fs max_attempts=%s",
        settings.worker_poll_interval_seconds,
        settings.worker_max_attempts,
    )
    run_worker_loop(
        session_factory,
        max_attempts=settings.worker_max_attempts,
        poll_interval_seconds=settings.worker_poll_interval_seconds,
        stop_event=stop_event,
    )
    logger.info("worker stopped")
    engine.dispose()


if __name__ == "__main__":
    main()
