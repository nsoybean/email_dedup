"""Directory loader: submit each file as document_id + payload to the API.

Filename is used only as the opaque document ID — structure is never interpreted.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True, slots=True)
class LoadSummary:
    submitted: int
    accepted: int
    already_completed: int
    conflicts: int
    errors: int


def iter_document_files(directory: Path) -> list[Path]:
    """Return sorted ``*.txt`` files; document_id will be ``path.name`` only."""
    return sorted(path for path in directory.iterdir() if path.is_file() and path.suffix == ".txt")


def submit_file(
    client: httpx.Client,
    path: Path,
    *,
    timeout: float = 30.0,
) -> tuple[str, int, dict]:
    """POST one file. Returns (document_id, status_code, response_json_or_error)."""
    document_id = path.name
    content = path.read_text(encoding="utf-8")
    response = client.post(
        "/documents",
        json={"document_id": document_id, "content": content},
        timeout=timeout,
    )
    try:
        body = response.json()
    except Exception:
        body = {"detail": response.text}
    return document_id, response.status_code, body


def load_directory(
    directory: Path,
    base_url: str,
    *,
    timeout: float = 30.0,
    client: httpx.Client | None = None,
) -> LoadSummary:
    """Submit every ``*.txt`` under ``directory`` to ``base_url``.

    Pass ``client`` to reuse an existing httpx client (e.g. ASGI test transport).
    """
    files = iter_document_files(directory)
    submitted = accepted = already_completed = conflicts = errors = 0
    owns_client = client is None

    if client is None:
        client = httpx.Client(base_url=base_url.rstrip("/"))

    try:
        for path in files:
            submitted += 1
            document_id, status_code, body = submit_file(client, path, timeout=timeout)
            if status_code == 202:
                status = body.get("status")
                if status == "completed":
                    already_completed += 1
                else:
                    accepted += 1
                print(f"202 {document_id} status={status} job_id={body.get('job_id')}")
            elif status_code == 409:
                conflicts += 1
                print(f"409 {document_id} conflict: {body.get('detail')}", file=sys.stderr)
            else:
                errors += 1
                print(
                    f"{status_code} {document_id} error: {body.get('detail', body)}",
                    file=sys.stderr,
                )
    finally:
        if owns_client:
            client.close()

    return LoadSummary(
        submitted=submitted,
        accepted=accepted,
        already_completed=already_completed,
        conflicts=conflicts,
        errors=errors,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Batch-submit a directory of email thread files to the ingestion API."
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory of .txt files (e.g. data/eval). Filenames become document IDs.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API base URL (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds",
    )
    args = parser.parse_args(argv)

    directory = args.directory
    if not directory.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2

    summary = load_directory(directory, args.base_url, timeout=args.timeout)
    print(
        f"submitted={summary.submitted} accepted={summary.accepted} "
        f"already_completed={summary.already_completed} "
        f"conflicts={summary.conflicts} errors={summary.errors}"
    )
    return 1 if summary.errors or summary.conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
