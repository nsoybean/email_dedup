# Email Ingestion and Deduplication

Prototype for the email ingestion and deduplication assignment.

See `DESIGN.md` for decisions and tradeoffs, `LEARNING.md` for FAQs.

## Run (kind)

Primary demo: a local [kind](https://kind.sigs.k8s.io/) Kubernetes cluster with
Postgres, migrate Job, API, and a **3-replica worker** Deployment. Ingest
**`data/test`**: each filename is the document ID; the service does not parse
filename structure. The corpus is included in the image for loader and evaluator
Jobs.

**Prerequisites:** Docker Desktop, [`kind`](https://kind.sigs.k8s.io/docs/user/quick-start/#installation),
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
make evaluate          # in-cluster scoring vs data/eval (expect status=PASS)
make ingest-eval       # optional: also load data/eval through workers
make cluster-down
```

| Make target | What it does |
|---|---|
| `cluster-up` | Create kind cluster, build/load `email-dedup:local`, apply `k8s/`, wait ready |
| `ingest` | Job: submit `data/test` to the API |
| `ingest-eval` | Job: submit `data/eval` |
| `evaluate` | Job: run `scripts/evaluate.py` modes (in-memory; needs no ingest) |
| `port-forward` | `svc/api` → `localhost:8000` |
| `status` | Pods / Deployments / Jobs |
| `cluster-down` | Delete the kind cluster |

| Workload | Role |
|---|---|
| `postgres` | Persistence + job queue |
| `migrate` | One-shot `alembic upgrade head` |
| `api` | Accept submissions; expose lookups |
| `worker` (3 replicas) | Parallel claim / parse / dedup into canonicals |

Workers share one Postgres queue (`FOR UPDATE SKIP LOCKED`). Scale with
`kubectl scale deployment/worker -n email-dedup --replicas=N`.

Images: `postgres:16-alpine`; `email-dedup:local` for migrate, API, workers,
loader, and evaluate.

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

Gold labels live in eval filenames for scoring only — never used by the app or
loader. Prefer `make evaluate` on kind. Locally:

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

```text
=== parsing ===
...
status=PASS
=== dedup ===
f1=1.0000
status=PASS
=== hierarchy order=natural ===
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
