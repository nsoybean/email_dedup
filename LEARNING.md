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
