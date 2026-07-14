# Email Ingestion and Deduplication

Prototype implementation for the email ingestion and deduplication assignment.

The project is being built incrementally. See `build_interactive_plan.md` for the
developer learning workflow, and `DESIGN.md` for findings and decisions.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . pytest ruff
```

## Validate parsing

```bash
source .venv/bin/activate
python scripts/evaluate.py parsing --data-dir data/eval
```

Example output:

```text
files_checked=202
parse_failures=0
count_mismatches=0
variant_sequence_mismatches=0
parent_sequence_mismatches=0
status=PASS
```

| Field | Meaning |
|---|---|
| `files_checked` | Number of eval `.txt` files examined |
| `parse_failures` | Files where `parse_thread` raised an error (e.g. missing Message-ID) |
| `count_mismatches` | Parsed message count ≠ gold count from filename depth (`1_0_0` → 3) |
| `variant_sequence_mismatches` | Near-duplicate files with the same gold label disagree on `message_ids` |
| `parent_sequence_mismatches` | Child’s `message_ids[1:]` does not equal its parent’s `message_ids` |
| `status` | `PASS` only if all of the above mismatch counts are 0 |

Gold label = eval filename with the trailing variant letter stripped
(`1_0_0b.txt` → `1_0_0`). Used only for scoring; see
[DESIGN.md — Eval filenames are gold labels only](DESIGN.md#eval-filenames-are-gold-labels-only)
and [how parsing validation works](DESIGN.md#parsing-validation-scriptsevaluatepy-parsing).

Unit tests for specific parse cases:

```bash
python -m pytest tests/unit/test_parser.py -v
```

## Validate deduplication

```bash
python scripts/evaluate.py dedup --data-dir data/eval
```

Pairwise clustering score over all document pairs:

| Field | Meaning |
|---|---|
| `true_positives` | Same gold label and same predicted `canonical_id` |
| `false_positives` | False merges: predicted same, gold different |
| `false_negatives` | False splits: gold same, predicted different |
| `precision` | `TP / (TP + FP)` |
| `recall` | `TP / (TP + FN)` |
| `f1` | Harmonic mean of precision and recall |
| `status` | `PASS` only if FP = FN = 0 and no parse failures |

See [DESIGN.md — Dedup validation](DESIGN.md#dedup-validation-scriptsevaluatepy-dedup).

```bash
python -m pytest tests/unit/test_canonicalization.py -v
```
