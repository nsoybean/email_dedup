---
name: email-ingestion-prototype
overview: Build a dataset-focused Python prototype that runs on a local kind Kubernetes cluster, batch-submits the bundled email files to FastAPI, processes them with concurrent PostgreSQL-backed worker pods, and exposes the required mappings through OpenAPI. Keep Docker Compose as a simpler fallback, while making Kubernetes the primary assignment demonstration.
todos:
  - id: scaffold
    content: "Phases 0-1: understand the corpus and scaffold the tested Python domain package"
    status: completed
  - id: parsing
    content: "Phase 2: implement and validate parsing across the eval corpus"
    status: completed
  - id: dedup
    content: "Phase 3: implement deterministic canonicalization and dedup evaluation"
    status: completed
  - id: hierarchy
    content: "Phase 4: implement order-independent hierarchy logic"
    status: completed
  - id: persistence
    content: "Phase 5: add PostgreSQL persistence, migrations, queue claiming, and integration tests"
    status: pending
  - id: api-workers
    content: "Phases 6-7: add FastAPI, the loader, concurrent workers, and Docker Compose"
    status: pending
  - id: regression
    content: "Phase 8: complete parsing, deduplication, and hierarchy regression evaluation"
    status: pending
  - id: kubernetes
    content: "Phase 9: deploy and verify the multi-worker system on local kind"
    status: pending
  - id: submission
    content: "Phase 10: finish reviewer documentation and final verification"
    status: pending
isProject: false
---

# Email Ingestion Prototype Plan

## Phased implementation
- This file is the authoritative implementation plan. [`build_interactive_plan.md`](build_interactive_plan.md) is only the developer-facing learning and command companion.
- Implement one phase at a time and keep each checkpoint runnable. Do not introduce PostgreSQL before pure parsing/dedup/hierarchy passes, and do not introduce Kubernetes before the application passes its local regression suite.

### Phase 0: Confirm corpus invariants
- Inspect representative root, child, branch, and variant documents from [`data/eval`](data/eval) and opaque documents from [`data/test`](data/test).
- Record the implementation assumptions in the eventual README: files are newest-first thread snapshots; ordered Message-ID sequences identify canonicals in this corpus; eval suffixes `b`/`c`/`d`/`e` identify variants; filename paths are evaluation truth only.
- Exit when the expected message count, canonical grouping, and parent rule can be derived for representative eval files without using filenames in ingestion logic.

### Phase 1: Scaffold the domain project
- Create [`pyproject.toml`](pyproject.toml), [`src/email_dedup`](src/email_dedup), and [`tests/unit`](tests/unit) with Python 3 typing, pytest, Ruff, application configuration, and basic immutable domain models.
- Keep the initial package independent of FastAPI, PostgreSQL, Docker, and Kubernetes.
- Add an import smoke test and establish `uv run pytest tests/unit` plus `uv run ruff check .` as the fast verification gate.

### Phase 2: Implement and validate parsing
- Implement a pure parser for top-level and quoted `From`/`Message-ID` headers, `|` and `>` quote prefixes, optional dash separators, reordered headers, blank-line differences, and newest-first ordering.
- Return typed parsed messages plus their exact ordered Message-ID sequence; treat missing or malformed IDs as explicit parse failures.
- Add focused fixtures and parameterized coverage in [`tests/unit/test_parser.py`](tests/unit/test_parser.py).
- Add the first evaluator mode in [`scripts/evaluate.py`](scripts/evaluate.py): filename depth checks expected message count, variants must share a sequence, and each child sequence without its newest ID must match its filename-derived parent.
- Exit when all 202 eval documents parse and parsing validation reports no count or sequence mismatches.

### Phase 3: Implement deterministic canonicalization
- Encode ordered Message-ID sequences unambiguously and derive canonical IDs with SHA-256.
- Implement pure grouping that maps each raw document to one canonical without any database or filename dependency.
- Add [`tests/unit/test_canonicalization.py`](tests/unit/test_canonicalization.py) for exact duplicates, formatting variants, distinct sequences, deterministic IDs, and malformed inputs.
- Add evaluator `dedup` mode: derive gold labels only inside evaluation, score pairwise TP/FP/FN (false merge / false split), and report precision, recall, F1 with pass/fail when FP=FN=0.
- Exit when variants map together, distinct eval canonicals remain separate, and repeated runs produce identical canonical IDs.

### Phase 4: Implement order-independent hierarchy
- Compute each non-root canonical’s `expected_parent_id` from its sequence with the newest Message-ID removed.
- Create canonical nodes only for observed raw documents. Resolve parent and children by deterministic IDs so child-first ingestion remains valid without placeholder ancestors.
- Add [`tests/unit/test_hierarchy.py`](tests/unit/test_hierarchy.py) for roots, chains, branches, missing parents, parent-later arrival, randomized ordering, and reverse ordering.
- Add evaluator `hierarchy` mode: derive gold edges from eval filenames and report edge precision, recall, F1, missing edges, and extra edges.
- Exit when normal, randomized, child-first, and reverse ingestion orders produce identical clusters and hierarchy edges.

### Phase 5: Add PostgreSQL persistence and job claiming
- Add SQLAlchemy repositories and Alembic migrations for `ingestion_jobs`, `raw_documents`, and `canonical_threads`.
- Enforce unique document IDs and canonical sequence hashes; index job status, canonical IDs, and `expected_parent_id`.
- Store raw payload hashes, job state/attempt/error metadata, ordered Message-IDs, and raw-to-canonical mappings.
- Implement short transactional upserts with `INSERT ... ON CONFLICT`, conflict detection for changed content under an existing document ID, and worker claims using `FOR UPDATE SKIP LOCKED`.
- Add PostgreSQL tests under [`tests/integration`](tests/integration) for clean migration, idempotent reprocessing, concurrent claims, retry state, and order-independent relation queries.
- Exit when multiple claimers cannot process the same queued job and all required query directions use indexed lookups.

### Phase 6: Add FastAPI and batch ingestion
- Implement asynchronous document submission, idempotent resubmission, conflict responses, health checks, and job-status endpoints.
- Implement `GET /documents/{doc_id}/canonical`, `GET /canonicals/{canonical_id}/documents`, and `GET /canonicals/{canonical_id}/relations`.
- Add a directory loader that submits filename as document ID and file contents as payload without interpreting filename structure.
- Add API integration tests, response schemas, and generated OpenAPI available at `/docs` and `/openapi.json`.
- Exit when the eval directory can be submitted locally and all required lookups can be exercised through OpenAPI.

### Phase 7: Add worker runtime and Docker Compose
- Implement a worker loop with bounded polling, transactional claims, retry limits, failed-job recording, and graceful shutdown.
- Add [`Dockerfile`](Dockerfile) and [`compose.yaml`](compose.yaml) for PostgreSQL, migrations, FastAPI, and at least three worker containers using one application image.
- Add health checks and dependency readiness without relying only on container startup order.
- Exit when three workers process randomized eval ingestion concurrently, retries are safe, and resubmission creates no duplicate mappings.

### Phase 8: Complete automated regression evaluation
- Finish `parsing`, `dedup`, `hierarchy`, and `all` modes in [`scripts/evaluate.py`](scripts/evaluate.py).
- Add [`tests/regression/test_eval_corpus.py`](tests/regression/test_eval_corpus.py) and preserve separation between unit, PostgreSQL integration, and corpus regression suites.
- Add `make validate-parsing`, `make validate-dedup`, `make validate-hierarchy`, and `make evaluate`; include actionable mismatch details, throughput, and completed/failed job counts.
- Exit when each validation stage passes independently and the combined report is stable across ingestion orders.

### Phase 9: Deploy and verify on local kind
- Add kind-compatible Kubernetes resources under [`k8s`](k8s) for configuration, secrets, PostgreSQL persistence, migrations, FastAPI, a three-replica worker Deployment, loader Jobs, evaluator Jobs, Services, and health probes.
- Add [`Makefile`](Makefile) automation: `cluster-up` creates kind, builds and loads the image, applies resources, and waits; `status`, `ingest-eval`, `evaluate`, and `cluster-down` demonstrate and clean up the system.
- Package the small assignment corpus into the exercise image for self-contained loader/evaluator Jobs, while documenting that production ingestion would use object storage or an event source.
- Exit when a fresh kind cluster processes eval data with at least three worker pods and produces the same metrics as local regression.

### Phase 10: Prepare the submission
- Write [`README.md`](README.md) with the shortest reviewer path first, architecture and data-flow diagrams, OpenAPI examples, eval results, scaling demonstration, assumptions, deliberate shortcuts, and troubleshooting.
- Document Docker’s role in building images, kind’s role as local Kubernetes, PostgreSQL’s role as storage and durable queue, and Compose as a fallback.
- Run linting, all test suites, all eval stages, a clean kind deployment, ingestion, evaluation, teardown, and repository hygiene checks.
- Exit when a reviewer can clone the repository and reproduce the assignment demonstration without undocumented steps.

## Architecture and interfaces
- Scaffold a Python 3 project in [`pyproject.toml`](pyproject.toml) with FastAPI, SQLAlchemy/Alembic, PostgreSQL, pytest, linting, and a container entrypoint.
- Build the service under [`src/email_dedup/`](src/email_dedup/) with three processes sharing one domain layer:
  - FastAPI accepts `doc_id` plus raw text, returns `202`, reports ingestion status, and serves interactive OpenAPI at `/docs` and `/openapi.json`.
  - A local batch loader scans `data/eval` or `data/test` and submits files to the API; no query CLI or dedicated Redis/RabbitMQ dependency.
  - Replicated workers claim PostgreSQL jobs with `FOR UPDATE SKIP LOCKED`, process them transactionally, and retry failed jobs.
- Expose the required reads as `GET /documents/{doc_id}/canonical`, `GET /canonicals/{canonical_id}/documents`, and `GET /canonicals/{canonical_id}/relations`.

## Parsing, canonicalization, and hierarchy
- Implement a custom plain-text parser that recognizes top-level and quoted `From`/`Message-ID` headers, both `|` and `>` quote prefixes, optional dash separators, reordered headers, and newest-first message order.
- Define a canonical thread by the exact ordered Message-ID sequence. Generate its stable ID from a SHA-256 digest of that sequence, making duplicate and variant ingestion deterministic and idempotent.
- This intentionally targets the supplied corpus: all observed eval near-duplicate variants share identical Message-ID sequences. Document that missing or mutated Message-IDs are rejected/flagged rather than silently merged by fuzzy content similarity.
- Infer a canonical parent from the child sequence with its newest Message-ID removed. Store its deterministic hash as `expected_parent_id`; create canonical rows only for observed raw documents, not synthetic ancestors. Parent and child queries resolve through indexed self-joins whenever the observed parent exists, making hierarchy construction independent of ingestion order and safe under concurrent workers.

## Persistence and concurrency
- Add Alembic migrations for `ingestion_jobs`, `raw_documents`, and `canonical_threads`, with uniqueness constraints for document IDs and sequence hashes.
- Store job payload/status/error metadata, raw-document-to-canonical mappings, ordered Message-ID arrays, and each canonical’s deterministic `expected_parent_id`. Index canonical IDs and expected parent IDs so parent/child relations are resolved without an order-sensitive edge table.
- Use short transactions plus `INSERT ... ON CONFLICT` to make repeated submissions and concurrent workers safe. Return a conflict when the same document ID is resubmitted with different content.

## Evaluation and tests
- Build evaluation as three independently runnable stages so each application layer can be validated before implementing the next:
  1. **Parsing validation:** derive expected message count from each normalized eval filename, require variants of one canonical label to produce the same ordered Message-ID sequence, and verify each child sequence without its newest ID equals its filename-derived parent sequence. Report files checked, parse failures, count mismatches, and sequence mismatches.
  2. **Deduplication validation:** ingest eval content without exposing filename structure to application code, derive gold canonical labels only inside the evaluator by stripping trailing variant letters, and compare predicted document pairs with gold pairs. Report pairwise precision, recall, F1, false merges, and false splits; generated canonical IDs need not match filename labels.
  3. **Hierarchy validation:** derive gold canonical edges by dropping the final numeric filename segment, compare them with content-derived parent/child relations, and report edge precision, recall, F1, missing edges, and extra edges. Repeat with randomized, child-first, and reverse ingestion orders and require identical final results after the queue drains.
- Implement these stages in [`scripts/evaluate.py`](scripts/evaluate.py) with `parsing`, `dedup`, `hierarchy`, and `all` modes. Add matching `make validate-parsing`, `make validate-dedup`, `make validate-hierarchy`, and `make evaluate` targets for iterative development locally and in kind.
- Keep filename-derived truth strictly inside the evaluation layer; the parser, workers, canonicalization domain, and APIs receive only document IDs and content and must not infer labels from eval names.
- Organize automated checks by scope: fast parser/canonicalization/hierarchy unit tests under [`tests/unit/`](tests/unit/), PostgreSQL concurrency and API tests under [`tests/integration/`](tests/integration/), and the complete 202-file corpus check under [`tests/regression/`](tests/regression/).
- Cover parser formats, deterministic grouping, branching, child-first ingestion, duplicate submission, and concurrent job claiming. Include processing throughput and completed/failed job counts in the full evaluation summary.

## Local Kubernetes delivery
- Make a local [`kind`](https://kind.sigs.k8s.io/) cluster the primary assignment demonstration. Add a production [`Dockerfile`](Dockerfile), [`Makefile`](Makefile), and resources under [`k8s/`](k8s/) for PostgreSQL, migrations, FastAPI, loader/evaluation Jobs, and a worker Deployment with three replicas.
- Automate the reviewer flow: `make cluster-up` creates the cluster, builds and loads the image, applies manifests, and waits for readiness; `make ingest-eval`, `make status`, `make evaluate`, and `make cluster-down` exercise and clean up the system.
- Package the small supplied corpus in the exercise image so Kubernetes loader/evaluation Jobs can run without host-volume assumptions. Document that a production system would submit content from object storage or an external event source instead.
- Expose FastAPI locally through `kubectl port-forward`, with OpenAPI available at `/docs`; demonstrate horizontal processing by showing and scaling the worker Deployment.
- Retain [`compose.yaml`](compose.yaml) as a simpler fallback for reviewers who do not have `kind` and `kubectl`, using the same image and multi-worker/PostgreSQL architecture.
- Document prerequisites, clone-to-run commands, OpenAPI examples, evaluation, schema, concurrency behavior, assumptions, observed dataset characteristics, and troubleshooting in [`README.md`](README.md). Include a concise architecture diagram and explain the roles of Docker, kind/Kubernetes, and PostgreSQL as the durable queue.