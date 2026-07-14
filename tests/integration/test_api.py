from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from email_dedup.api.app import create_app
from email_dedup.db.repository import claim_next_job, process_job
from tests.integration.conftest import read_eval

pytestmark = pytest.mark.integration


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> TestClient:
    app = create_app(session_factory=session_factory)
    return TestClient(app)


def _drain_queue(session_factory: sessionmaker[Session]) -> int:
    """Process all pending jobs (stand-in for Phase 7 workers)."""
    processed = 0
    while True:
        with session_factory() as session:
            job = claim_next_job(session)
            if job is None:
                session.commit()
                return processed
            process_job(session, job)
            session.commit()
            processed += 1


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "up"}


def test_openapi_available(client: TestClient) -> None:
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    for path in (
        "/documents",
        "/jobs/{job_id}",
        "/documents/{doc_id}/canonical",
        "/canonicals/{canonical_id}/documents",
        "/canonicals/{canonical_id}/relations",
        "/health",
    ):
        assert path in paths

    docs = client.get("/docs")
    assert docs.status_code == 200


def test_submit_idempotent_and_conflict(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    payload = read_eval("1.txt")
    first = client.post(
        "/documents",
        json={"document_id": "1.txt", "content": payload},
    )
    assert first.status_code == 202
    body = first.json()
    assert body["status"] == "pending"
    assert body["job_id"] is not None
    job_id = body["job_id"]

    pending_again = client.post(
        "/documents",
        json={"document_id": "1.txt", "content": payload},
    )
    assert pending_again.status_code == 202
    assert pending_again.json()["job_id"] == job_id

    status = client.get(f"/jobs/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "pending"
    assert status.json()["document_id"] == "1.txt"

    processed = _drain_queue(session_factory)
    assert processed == 1

    completed = client.get(f"/jobs/{job_id}")
    assert completed.json()["status"] == "completed"

    again = client.post(
        "/documents",
        json={"document_id": "1.txt", "content": payload},
    )
    assert again.status_code == 202
    assert again.json()["status"] == "completed"
    assert again.json()["job_id"] is None
    assert again.json()["canonical_id"] is not None

    conflict = client.post(
        "/documents",
        json={"document_id": "1.txt", "content": read_eval("1_0.txt")},
    )
    assert conflict.status_code == 409
    assert "different content" in conflict.json()["detail"]


def test_assignment_lookups_via_api(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    for name in ("1_0_0.txt", "1_0_0b.txt", "1_0.txt", "1.txt"):
        response = client.post(
            "/documents",
            json={"document_id": name, "content": read_eval(name)},
        )
        assert response.status_code == 202

    assert _drain_queue(session_factory) == 4

    child = client.get("/documents/1_0_0.txt/canonical")
    assert child.status_code == 200
    child_canonical = child.json()["canonical_id"]

    variant = client.get("/documents/1_0_0b.txt/canonical")
    assert variant.status_code == 200
    assert variant.json()["canonical_id"] == child_canonical

    docs = client.get(f"/canonicals/{child_canonical}/documents")
    assert docs.status_code == 200
    assert docs.json()["document_ids"] == ["1_0_0.txt", "1_0_0b.txt"]

    mid = client.get("/documents/1_0.txt/canonical").json()["canonical_id"]
    root = client.get("/documents/1.txt/canonical").json()["canonical_id"]

    child_rel = client.get(f"/canonicals/{child_canonical}/relations")
    assert child_rel.status_code == 200
    assert child_rel.json()["parent_id"] == mid
    assert child_rel.json()["child_ids"] == []

    mid_rel = client.get(f"/canonicals/{mid}/relations")
    assert mid_rel.json()["parent_id"] == root
    assert child_canonical in mid_rel.json()["child_ids"]

    root_rel = client.get(f"/canonicals/{root}/relations")
    assert root_rel.json()["parent_id"] is None
    assert mid in root_rel.json()["child_ids"]


def test_lookup_not_found(client: TestClient) -> None:
    assert client.get("/documents/missing.txt/canonical").status_code == 404
    assert client.get("/canonicals/" + ("a" * 64) + "/documents").status_code == 404
    assert client.get("/canonicals/" + ("b" * 64) + "/relations").status_code == 404
    assert client.get("/jobs/999999").status_code == 404


def test_loader_submits_eval_filenames_as_doc_ids(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Loader uses path.name only — no filename structure interpretation."""
    import tempfile
    from pathlib import Path

    from email_dedup.loader import iter_document_files

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name in ("1.txt", "1_0.txt"):
            (tmp_path / name).write_text(read_eval(name), encoding="utf-8")

        files = iter_document_files(tmp_path)
        assert [p.name for p in files] == ["1.txt", "1_0.txt"]

        for path in files:
            response = client.post(
                "/documents",
                json={
                    "document_id": path.name,
                    "content": path.read_text(encoding="utf-8"),
                },
            )
            assert response.status_code == 202
            assert response.json()["document_id"] == path.name
            assert response.json()["status"] == "pending"
            assert response.json()["job_id"] is not None

    assert _drain_queue(session_factory) == 2
    assert client.get("/documents/1.txt/canonical").status_code == 200
    assert client.get("/documents/1_0.txt/canonical").status_code == 200
