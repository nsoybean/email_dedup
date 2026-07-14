# Email Ingestion and Deduplication

Prototype that ingests raw email thread dumps, deduplicates them into canonical
threads by Message-ID sequence, and links parent/child hierarchy — with parallel
workers on local Kubernetes ([kind](https://kind.sigs.k8s.io/)).

See `DESIGN.md` for decisions and tradeoffs, `LEARNING.md` for FAQs.

## Run (kind)

Primary demo: a local [kind](https://kind.sigs.k8s.io/) Kubernetes cluster with
Postgres, migrate Job, API, and a **3-replica worker** Deployment. Ingest
`data/test`: each filename is the document ID; the service does not parse
filename structure. The corpus is included in the image for loader and evaluator
Jobs.

**Prerequisites:** Docker Desktop,
[kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation),
`kubectl`, `make`.

If Compose is already running, stop it first so ports/resources do not clash:
`docker compose down`.

```bash
make cluster-up
make ingest
make port-forward
# OpenAPI: http://127.0.0.1:8000/docs
```

Other terminals:

```bash
make status
make evaluate          # score parse / dedup / hierarchy vs data/eval (expect PASS)
make cluster-down
```

| Make target | What it does |
|---|---|
| `cluster-up` | Create kind cluster, build/load `email-dedup:local`, apply `k8s/`, wait ready |
| `ingest` | Job: submit `data/test` to the API. This starts async ingestion |
| `port-forward` | `svc/api` → `localhost:8000` |
| `status` | Pods / Deployments / Jobs |
| `evaluate` | Score parse / dedup / hierarchy against `data/eval` (in-memory) |
| `cluster-down` | Delete the kind cluster |

| Workload | Role |
|---|---|
| `postgres` | Persistence + durable job queue |
| `migrate` | One-shot `alembic upgrade head` |
| `api` | Server for job submissions and query lookups |
| `worker` (3 replicas) | Parallel claim / parse / dedup into canonicals |

Workers share one Postgres queue (`FOR UPDATE SKIP LOCKED`). Scale with:

```bash
kubectl scale deployment/worker -n email-dedup --replicas=5
make status   # expect worker Ready 5/5
```

### API

Interactive OpenAPI (after `make port-forward`):
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness + DB ping |
| `POST` | `/documents` | Submit `{document_id, content}` → 202 (409 on conflict) |
| `GET` | `/jobs/{job_id}` | Job status |
| `GET` | `/documents/{doc_id}/canonical` | Raw doc → canonical |
| `GET` | `/canonicals/{canonical_id}/documents` | Canonical → raw docs |
| `GET` | `/canonicals/{canonical_id}/relations` | Direct parent + children |

After ingest, try in `/docs` or with curl:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/documents/doc1.txt/canonical
# → {"document_id":"doc1.txt","canonical_id":"<sha256...>"}
curl -s "http://127.0.0.1:8000/canonicals/<canonical_id>/documents"
curl -s "http://127.0.0.1:8000/canonicals/<canonical_id>/relations"
```

## Architecture

```mermaid
flowchart LR
  loader[Loader Job<br/>data/test]
  api[API]
  pg[(PostgreSQL)]
  workers[Worker(s)]
  docs[OpenAPI lookups]

  loader -->|"POST /documents"| api
  api -->|"enqueue job<br/>status=pending"| pg
  workers -->|"claim FOR UPDATE<br/>SKIP LOCKED"| pg
  workers -->|"parse → canonical<br/>+ parent edge"| pg
  docs -->|"GET canonical / docs / relations"| api
  api --> pg
```

Near-dedup uses exact ordered Message-ID sequences
(`canonical_id = sha256(join(ids))`). Each child stores
`expected_parent_id = hash(message_ids[1:])`; `GET …/relations` resolves
`parent_id` with a join only when that parent row already exists in
`canonical_threads` (child-first ingest is fine; the parent appears later).
See [DESIGN.md — Hierarchy](DESIGN.md#hierarchy) and
[Persistence](DESIGN.md#persistence).

## Fallback: Docker Compose

Same image and three workers, without Kubernetes:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

docker compose up --build -d
python scripts/load_directory.py data/test --base-url http://127.0.0.1:8000
# OpenAPI: http://127.0.0.1:8000/docs
docker compose down
```

## Evaluate (`data/eval`)

Filenames in `data/eval` encode ground truth (canonical groups, parent links).
The evaluator **parses those names** only to score parse / dedup / hierarchy —
the app and loader never use them. Prefer `make evaluate` on kind (in-memory;
does not load eval into the DB). Locally:

```bash
source .venv/bin/activate
python scripts/evaluate.py parsing --data-dir data/eval
python scripts/evaluate.py dedup --data-dir data/eval
python scripts/evaluate.py hierarchy --data-dir data/eval
python scripts/evaluate.py hierarchy --data-dir data/eval --order reverse
python scripts/evaluate.py hierarchy --data-dir data/eval --order child_first
python scripts/evaluate.py hierarchy --data-dir data/eval --order random --seed 1
```

Expect every run to end with `status=PASS` (and hierarchy `order_independent=True`).

| Mode | Measures |
|---|---|
| `parsing` | Parse failures, count vs gold depth, variant sequences, parent rule — [details](DESIGN.md#parsing-validation-scriptsevaluatepy-parsing) |
| `dedup` | Pairwise precision / recall / F1 — [details](DESIGN.md#dedup-validation-scriptsevaluatepy-dedup) |
| `hierarchy` | Edge F1; order-independence — [details](DESIGN.md#hierarchy-validation-scriptsevaluatepy-hierarchy) |

Gold labels: [DESIGN.md](DESIGN.md#eval-filenames-are-gold-labels-only).

Observed on `data/eval` (202 files):

```text
=== parsing ===
files_checked=202
parse_failures=0
status=PASS

=== dedup ===
unique_gold_labels=98
f1=1.0000
status=PASS

=== hierarchy order=natural ===
f1=1.0000
order_independent=True
status=PASS
```

## Tests

```bash
source .venv/bin/activate
pytest tests/unit -v

docker compose up -d postgres
alembic upgrade head
pytest tests/integration -v
```

Default DB: `postgresql+psycopg://email:email@localhost:5433/email_dedup`
(`DATABASE_URL` to override).

## Assumptions and shortcuts

| Choice | Note |
|---|---|
| Message-ID sequence equality for near-dedup | Matches this corpus; missing/mutated IDs fail rather than fuzzy-merge |
| Postgres as DB **and** job queue | Fewer moving parts; production would often add a dedicated broker |
| Full payload on each job row | Workers need no shared volume; production might store objects in S3 |
| Corpus in the image | Convenient for kind Jobs; production would use object storage / events |
| Observed-only parents | Child stores `expected_parent_id`; parent appears in relations once ingested |
| Direct parent/children API only | Assignment asks one-hop lookups, not full ancestry walks |

## Troubleshooting

| Problem | What to try |
|---|---|
| `kind` not found | Install from [kind quick start](https://kind.sigs.k8s.io/docs/user/quick-start/#installation); `Makefile` also checks `~/bin/kind` |
| Port or Docker conflict with Compose | `docker compose down` before `make cluster-up` |
| API image out of date after code change | `make build load` then `kubectl rollout restart deployment/api deployment/worker -n email-dedup` |
| Lookups 404 right after ingest | Wait a few seconds for workers to drain; check `kubectl logs -n email-dedup deploy/worker --tail=30` |
| Migrate / loader Job stuck | `make status`; `kubectl describe job -n email-dedup …`; `kubectl logs -n email-dedup job/…` |
| Reset everything | `make cluster-down` then `make cluster-up` |
