# Interactive Build and Learning Plan

Build one phase at a time. At the end of each phase, run its checks, inspect the output, and ask the AI to explain the implementation before continuing. Do not ask the AI to implement later phases early.

## Phase 0: Understand the dataset and target behavior

### Build
- Make no application changes.
- Inspect representative files from `data/eval` and `data/test`.
- Write down the core invariants:
  - A file is a newest-first snapshot of one email chain.
  - The ordered Message-ID sequence identifies a canonical thread in this dataset.
  - Eval filename letters (`b`, `c`, `d`, `e`) indicate variants of the same canonical thread.
  - Removing the final numeric filename segment gives the gold parent label.

### Learn
- Why filenames are allowed in evaluation but prohibited as ingestion signals.
- Why a branching hierarchy differs from a linear thread.
- Why ingestion order must not affect final results.

### Run and inspect
```bash
ls data/eval
less data/eval/1.txt
less data/eval/1_0.txt
less data/eval/1_0_0b.txt
```

### Exit criteria
- You can manually explain why `1_0_0.txt` and `1_0_0b.txt` should deduplicate.
- You can explain why `1_0` is the parent of `1_0_0`.

## Phase 1: Scaffold the Python project

### Build
- Add `pyproject.toml`, the `src/email_dedup/` package, pytest configuration, Ruff, and basic typed domain models.
- Keep this phase independent of FastAPI, PostgreSQL, Docker, and Kubernetes.
- Add a trivial smoke test proving the package imports.

### Learn
- The `src/` package layout and dependency groups.
- The difference between domain code and infrastructure code.
- How pytest discovery and Ruff checks work.

### Run and inspect
```bash
uv sync --all-groups
uv run pytest tests/unit
uv run ruff check .
```

### Exit criteria
- The package imports successfully.
- Unit tests and linting pass.

## Phase 2: Parse email thread snapshots

### Build
- Implement a pure parser that extracts an ordered newest-first list of messages and Message-IDs.
- Support top-level headers, `|` and `>` quote prefixes, optional dash separators, reordered headers, and varying date formats without depending on dates.
- Add focused fixtures and parameterized unit tests in `tests/unit/test_parser.py`.
- Add the `parsing` mode to `scripts/evaluate.py`.

### Learn
- Why parsing these files is different from parsing complete MIME email.
- How boundary detection and quote-prefix normalization work.
- Why Message-ID extraction is more reliable than subject matching for this corpus.

### Run and inspect
```bash
uv run pytest tests/unit/test_parser.py -v
uv run python scripts/evaluate.py parsing --data-dir data/eval
```

Expected validation:
- Message count matches normalized filename depth plus one.
- Variants of the same gold label produce identical ordered Message-ID sequences.
- A parsed child sequence without its newest ID matches its parsed parent.

### Exit criteria
- All 202 eval files parse.
- The parsing report has no message-count or sequence mismatches.

## Phase 3: Implement deterministic deduplication

### Build
- Define a canonical key as SHA-256 over a stable encoding of the ordered Message-ID sequence.
- Implement pure canonical grouping with no database dependency.
- Add unit tests in `tests/unit/test_canonicalization.py`.
- Add the `dedup` mode to `scripts/evaluate.py`; only this evaluation layer may derive gold labels by stripping filename variant letters.

### Learn
- Why deterministic keys make retries and concurrent ingestion idempotent.
- Pairwise precision, recall, and F1.
- TP / FP / FN for clustering: false positive = false merge, false negative = false split.
- The deliberate limitation: missing or mutated Message-IDs are reported instead of fuzzy-matched.

### Run and inspect
```bash
source .venv/bin/activate
python -m pytest tests/unit/test_canonicalization.py -v
python scripts/evaluate.py dedup --data-dir data/eval
```

### Exit criteria
- Variant files map to the same predicted canonical.
- Distinct gold canonicals remain separate.
- Report shows `false_positives=0`, `false_negatives=0`, and `status=PASS`.

## Phase 4: Build an order-independent hierarchy

### Build
- Compute `expected_parent_id` from the sequence with its newest Message-ID removed.
- Create canonicals only for observed raw documents; do not create placeholder ancestors.
- Resolve parents and children by deterministic IDs.
- Add branching, child-first, randomized-order, and reverse-order tests in `tests/unit/test_hierarchy.py`.
- Add the `hierarchy` mode to `scripts/evaluate.py`.

### Learn
- Eventual resolution when a child arrives before its parent.
- Why deterministic relationships avoid parent-first ingestion requirements.
- Edge precision, recall, and F1.

### Run and inspect
```bash
source .venv/bin/activate
python -m pytest tests/unit/test_hierarchy.py -v
python scripts/evaluate.py hierarchy --data-dir data/eval
python scripts/evaluate.py hierarchy --data-dir data/eval --order random --seed 1
python scripts/evaluate.py hierarchy --data-dir data/eval --order reverse
```

### Exit criteria
- Normal, randomized, child-first, and reverse ingestion orders produce identical clusters and edges.
- Branching parents return all expected children.
- Report shows `false_positives=0`, `false_negatives=0`, `order_independent=True`, `status=PASS`.

## Phase 5: Add PostgreSQL persistence and the durable job queue

### Build
- Add SQLAlchemy models and Alembic migrations for `ingestion_jobs`, `raw_documents`, and `canonical_threads`.
- Store ordered Message-IDs and indexed `expected_parent_id`.
- Implement idempotent upserts and PostgreSQL job claiming with `FOR UPDATE SKIP LOCKED`.
- Add integration tests under `tests/integration/`.

### Learn
- Transactions, unique constraints, and `INSERT ... ON CONFLICT`.
- How `SKIP LOCKED` distributes work without two workers claiming the same job.
- Why PostgreSQL is sufficient as the prototype queue.

### Run and inspect
```bash
docker compose up -d postgres
uv run alembic upgrade head
uv run pytest tests/integration -v
```

Inspect tables and claimed jobs through `psql` or a database client.

### Exit criteria
- Migrations apply to an empty database.
- Repeated ingestion is idempotent.
- Concurrent claim tests show each job is processed once.

## Phase 6: Add FastAPI and the local batch loader

### Build
- Add asynchronous ingestion and job-status endpoints.
- Add the three required query endpoints:
  - raw document to canonical
  - canonical to raw documents
  - canonical to resolved parent and children
- Add a loader that submits every file in a directory without interpreting its filename.
- Add API tests.

### Learn
- The boundary between accepting work and processing work.
- HTTP `202 Accepted`, idempotency, and conflict behavior.
- How FastAPI generates `/docs` and `/openapi.json`.

### Run and inspect
```bash
docker compose up -d postgres
uv run uvicorn email_dedup.api:app --reload
```

In another terminal:
```bash
uv run python -m email_dedup.loader data/eval --api-url http://localhost:8000
open http://localhost:8000/docs
```

### Exit criteria
- A directory can be submitted.
- Job status is visible.
- All required queries work through OpenAPI.

## Phase 7: Run multiple workers locally

### Build
- Implement the worker loop, retries, graceful shutdown, and failed-job recording.
- Complete `compose.yaml` with PostgreSQL, migrations, API, and at least three workers.
- Add health checks and deterministic startup ordering.

### Learn
- Worker lifecycle and at-least-once delivery.
- Why idempotent processing is necessary even when claims are locked.
- How concurrent workers affect ordering but not final state.

### Run and inspect
```bash
docker compose up --build --scale worker=3
docker compose ps
docker compose logs -f worker
```

Submit eval files in randomized order and observe different workers claiming jobs.

### Exit criteria
- Multiple workers process jobs concurrently.
- No document is lost or mapped inconsistently.
- Re-running the loader does not create duplicate records.

## Phase 8: Run the complete eval regression

### Build
- Finish `scripts/evaluate.py all`.
- Add `tests/regression/test_eval_corpus.py`.
- Keep fast unit tests separate from database integration and corpus regression tests.
- Add Make targets for each validation layer.

### Learn
- Unit versus integration versus regression testing.
- Why aggregate metrics should also include actionable mismatch details.
- How to detect an application-logic regression before Kubernetes is introduced.

### Run and inspect
```bash
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/regression
make validate-parsing
make validate-dedup
make validate-hierarchy
make evaluate
```

Test layout:
```text
tests/unit/test_parser.py
tests/unit/test_canonicalization.py
tests/unit/test_hierarchy.py
tests/integration/test_concurrent_ingestion.py
tests/integration/test_api.py
tests/regression/test_eval_corpus.py
```

### Exit criteria
- All three validation reports pass independently.
- The full report includes parsing failures, pairwise dedup metrics, hierarchy edge metrics, throughput, and job counts.

## Phase 9: Deploy the same system to local Kubernetes

### Build
- Add the application Docker image.
- Add kind-compatible manifests for PostgreSQL, migrations, FastAPI, three worker replicas, loader, and evaluator Jobs.
- Automate image loading and deployment through the Makefile.
- Keep Docker Compose as a fallback, but use kind as the assignment demonstration.

### Learn
- Docker images versus Kubernetes pods.
- Deployments, replicas, Services, Jobs, ConfigMaps, Secrets, and StatefulSets.
- How Kubernetes restarts and scales workers.

### Run and inspect
```bash
make cluster-up
make status
make ingest-eval
make evaluate
kubectl get pods
kubectl scale deployment/worker --replicas=4
kubectl get pods
make cluster-down
```

Port-forward the API when needed:
```bash
kubectl port-forward service/api 8000:8000
```

### Exit criteria
- A fresh kind cluster reaches a healthy state from documented commands.
- Three or more worker pods process eval ingestion.
- Kubernetes evaluation matches the local regression result.

## Phase 10: Submission documentation and final verification

### Build
- Write `README.md` with a short reviewer path, architecture diagram, API examples, evaluation output, assumptions, tradeoffs, and troubleshooting.
- Document the dataset-specific Message-ID assumption and production extensions.
- Ensure no credentials, generated database files, or local artifacts are committed.

### Learn
- How to explain prototype shortcuts without presenting them as production guarantees.
- How to demonstrate correctness, efficiency, and scalability against the assignment rubric.

### Run and inspect
```bash
uv run ruff check .
uv run pytest
make cluster-up
make ingest-eval
make evaluate
make cluster-down
git status
```

### Exit criteria
- A reviewer can clone the repository and follow the README without undocumented steps.
- Tests, all three eval stages, Docker Compose, and the kind demonstration succeed.

## Suggested interactive AI workflow

For each phase:

1. Ask the AI to implement only the current phase.
2. Review the changed files before running commands.
3. Ask the AI to explain one unfamiliar design choice or code path.
4. Run the phase commands yourself.
5. Share failures with the AI and diagnose them before changing scope.
6. Confirm the exit criteria.
7. Commit the completed phase if desired, then start the next phase.

Useful prompts:

```text
Implement only Phase 2 from build_interactive_plan.md. Stop after its exit criteria can be tested.
```

```text
Explain the parser boundary logic and walk me through one eval file before we continue.
```

```text
Run the Phase 4 checks, explain any hierarchy mismatch, and do not begin Phase 5.
```
