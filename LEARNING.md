# Learning Log

Durable learning checkpoints for this project. The build plan lives in
`.cursor/plans/` — this file is only **what was built** plus **FAQ** for review
after each phase.

Agents should:
- Teach live in chat when asked
- After each phase, append a short section here (do not dump the whole chat)
- Include both **planned** learn questions and **discovered** FAQs from
  implementation surprises
- Prefer Q&A that you can re-read later without the conversation

---

## Phase 0–1 — Scaffold + corpus understanding

**Built:** Python package layout, `RawDocument` / settings, unit/lint gate.

### FAQ

**Q: What is a gold label?**  
A: Eval filename with trailing variant letter stripped (`1_0_0b.txt` → `1_0_0`).
Scoring only — never used during ingestion.

**Q: Why is `1_0` the parent of `1_0_0`?**  
A: Newest-first Message-ID sequences: parent is `message_ids[1:]`. Filename rule
mirrors that by dropping the last path segment.

---

## Phase 2 — Parsing

**Built:** `parse_thread`, parsing eval mode, parser unit tests.

### FAQ

**Q: Why not a MIME library?**  
A: These files are plain-text thread dumps with `|`/`>` quotes, not MIME parts.

**Q: What is “double-space gt”?**  
A: Quoted headers like `>  From:` (two spaces after `>`). Parser must use `>\s*`.

**Q: What does `scripts/evaluate.py parsing` check?**  
A: Parse failures, message-count vs gold depth, variant sequence equality, and
`child.message_ids[1:] == parent.message_ids`.

---

## Phase 3 — Deduplication / canonicalization

**Built:** `canonical_id = sha256(join(message_ids, "\n"))`, dedup eval with
TP/FP/FN + precision/recall/F1.

### FAQ

**Q: Do near-duplicates each get their own canonical id?**  
A: No. Same Message-ID sequence → same `canonical_id`. Raw `document_id`s stay unique.

**Q: Why F1 instead of only accuracy?**  
A: Most pairs are true negatives; accuracy stays high even with bad merges/splits.
F1 focuses on “should these two be the same?”. Assignment allows non-100%.

**Q: What are FP / FN here?**  
A: FP = false merge (predicted same, gold different). FN = false split (gold same,
predicted different).

---

## Phase 4 — Hierarchy

**Built:** `expected_parent_id`, observed-only `CanonicalStore`, hierarchy eval +
order-independence checks.

### FAQ

**Q: Does ingestion order matter?**  
A: No for final state. IDs are deterministic; parent/child resolve by JOIN when both
nodes are observed.

**Q: What is an observed parent?**  
A: A canonical we have ingested at least one raw document for. Child always stores
`expected_parent_id`; parent is unresolved until that id exists in the store.

**Q: Do long chains need many queries for the assignment API?**  
A: No. Assignment asks only direct parent/children (one hop).

---

## Phase 5 — PostgreSQL persistence

**Built:** SQLAlchemy models, Alembic migration, Compose Postgres on **5433**,
enqueue/claim/process, integration tests.

### FAQ

**Q: SQLAlchemy vs Alembic?**  
A: SQLAlchemy = ORM/SQL in Python. Alembic = versioned schema migrations.

**Q: Does a job store the file path or the content?**  
A: Full payload in `ingestion_jobs`. Workers don’t need a shared disk mount.

**Q: Why Postgres as the job queue?**  
A: Dirty prototype: `FOR UPDATE SKIP LOCKED` gives parallel workers without Redis.
Production would usually use a dedicated broker and keep Postgres for state.

**Q: Why did integration tests fail with password errors on 5432?**  
A: Another local Postgres (Langfuse) already bound 5432. This project uses 5433.

---

## Phase 6 — FastAPI + batch loader

**Built:** FastAPI submit/health/job-status + assignment lookups; directory
loader; OpenAPI at `/docs`; API integration tests.

### FAQ

**Q: Why does `POST /documents` return 202 instead of writing canonicals immediately?**  
A: Ingestion is async. The API enqueues a job; workers (Phase 7) claim and
process. Lookups only succeed after a job completes.

**Q: What does idempotent resubmission mean here?**  
A: Same `document_id` + same content → 202 again (reuse pending job, or
`status=completed` if already processed). Same id + different content → 409.

**Q: Does the loader parse eval filenames like `1_0_0b`?**  
A: No. `path.name` is the opaque `document_id`. Gold labels stay in the
evaluator only.

**Q: How do I try the API locally before workers exist?**  
A: Prefer the Compose stack below (Phase 7). Or run API alone with
`uvicorn email_dedup.api.app:app --reload` — jobs stay `pending` until a worker
drains them. OpenAPI UI: `http://127.0.0.1:8000/docs`.

**Q: What are `schemas.py` vs `deps.py`?**  
A: `schemas.py` = Pydantic request/response shapes (OpenAPI). `deps.py` =
FastAPI dependencies that inject things into routes (here, a DB session).

**Q: Is `get_db_session` a singleton Session?**  
A: No. `app.state.session_factory` is shared (one engine/pool). Each request
gets a **new** Session: yield → commit on success / rollback on error → close.
See docstring on `get_db_session` in `api/deps.py`.

---

## Phase 7 — Workers + Docker Compose

**Built:** Worker loop (claim → process → retry/fail, SIGTERM shutdown);
`Dockerfile`; Compose with migrate + API + three workers; worker integration
tests.

### FAQ

**Q: Why commit the claim before processing?**  
A: If process fails and you `rollback`, an uncommitted claim would also undo
`attempts += 1`, so retries never advance. Claim in its own transaction first.

**Q: What gets retried vs failed immediately?**  
A: Transient errors (e.g. unexpected RuntimeError) requeue until
`WORKER_MAX_ATTEMPTS`. `ParseError` / `DocumentConflictError` fail immediately.

**Q: One image for API and workers — how?**  
A: Same Dockerfile; Compose overrides `command` (`uvicorn` vs
`python -m email_dedup.worker`). Migrate is a one-shot of the same image.

**Q: How does Compose avoid “started before DB ready”?**  
A: Postgres `healthcheck` + migrate `service_completed_successfully` + API/worker
`depends_on` those conditions (not just container start).

---

## Phase 9 — kind Kubernetes

**Built:** `k8s/` manifests, Makefile (`cluster-up` / ingest / evaluate /
`cluster-down`), kind-first README; Phase 8 packaging deferred.

### FAQ

**Q: Why kind if Compose already has three workers?**  
A: Compose shows concurrent processing. kind shows the same app on a real
Kubernetes API (Deployments, Jobs, Services, probes) — the assignment’s K8s
requirement. They are alternatives, not meant to run together.

**Q: Compose vs kind — conflicting?**  
A: No. Same image and domain logic. Stop Compose before `make cluster-up` if
both would fight over Docker resources.

**Q: Why is the worker a Deployment with replicas=3?**  
A: Kubernetes scales identical pods. Each pod runs `python -m email_dedup.worker`
and claims via `SKIP LOCKED`. Change count with `kubectl scale`.

**Q: Why bake `data/` into the image?**  
A: Loader/evaluator Jobs need files without host volume mounts. Production would
pull from object storage or an event source instead.

---

## Phase 10 — Submission README

**Built:** Reviewer-facing README with kind path first, data-flow mermaid
(Postgres as store + queue), OpenAPI examples, eval sample, scale, assumptions,
troubleshooting.

### FAQ

**Q: Why show Postgres as the queue in the diagram instead of an abstract “queue”?**  
A: Hiding it makes the design look like Redis/SQS. Showing `enqueue` +
`SKIP LOCKED` claim is the deliberate prototype choice — clearer for reviewers.

**Q: Who uses `data/test` vs `data/eval`?**  
A: `data/test` → ingest into the system. `data/eval` → in-memory scoring only
(`make evaluate`); never loaded as the primary demo corpus.
