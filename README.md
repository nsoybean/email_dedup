# Email Ingestion and Deduplication

Prototype for the email ingestion and deduplication assignment.

See `DESIGN.md` for decisions and tradeoffs, `LEARNING.md` for FAQs.

## Run

Requires Docker Desktop. One app image runs migrate, FastAPI, and three workers
against PostgreSQL. Load **`data/test`** (opaque filenames = document IDs only).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

docker compose up --build -d
python scripts/load_directory.py data/test --base-url http://127.0.0.1:8000
```

| | |
|---|---|
| OpenAPI | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) |
| Health | [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) |
| Status | `docker compose ps` |
| Worker logs | `docker compose logs worker-1 --tail 20` |
| Stop | `docker compose down` |

| Service | Role |
|---|---|
| `postgres` | Persistence + job queue (host **5433**) |
| `migrate` | One-shot `alembic upgrade head` |
| `api` | Accept submissions; expose lookups |
| `worker-1/2/3` | Parallel processing: claim jobs, parse threads, dedup into canonicals |

The three workers pull from the same Postgres queue (`FOR UPDATE SKIP LOCKED`)
so documents are processed concurrently. Worker count is fixed in `compose.yaml`
(three named services); change it by adding or removing a `worker-N` block.

Images: `postgres:16-alpine`; `email-dedup:local` for migrate, API, and workers.

### API

Interactive OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness + DB ping |
| `POST` | `/documents` | Submit `{document_id, content}` → 202 (409 on conflict) |
| `GET` | `/jobs/{job_id}` | Job status |
| `GET` | `/documents/{doc_id}/canonical` | Raw doc → canonical |
| `GET` | `/canonicals/{canonical_id}/documents` | Canonical → raw docs |
| `GET` | `/canonicals/{canonical_id}/relations` | Direct parent + children |

## Evaluate (`data/eval`)

Gold labels live in eval filenames for scoring only — never used by the app or
loader. Expect every run to end with `status=PASS` (and hierarchy
`order_independent=True`).

```bash
source .venv/bin/activate
python scripts/evaluate.py parsing --data-dir data/eval
python scripts/evaluate.py dedup --data-dir data/eval
python scripts/evaluate.py hierarchy --data-dir data/eval
python scripts/evaluate.py hierarchy --data-dir data/eval --order reverse
python scripts/evaluate.py hierarchy --data-dir data/eval --order child_first
python scripts/evaluate.py hierarchy --data-dir data/eval --order random --seed 1
```

| Mode | Measures |
|---|---|
| `parsing` | Parse failures, count vs gold depth, variant sequences, parent rule — [details](DESIGN.md#parsing-validation-scriptsevaluatepy-parsing) |
| `dedup` | Pairwise precision / recall / F1 — [details](DESIGN.md#dedup-validation-scriptsevaluatepy-dedup) |
| `hierarchy` | Edge F1; order-independence — [details](DESIGN.md#hierarchy-validation-scriptsevaluatepy-hierarchy) |

Gold labels: [DESIGN.md](DESIGN.md#eval-filenames-are-gold-labels-only).

Example (abbreviated):

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
