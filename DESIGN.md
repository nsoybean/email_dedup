# Design Notes

Living notes for this prototype: dataset findings, architecture decisions,
tradeoffs, and assumptions. Update while building.

## Findings

### What each file is

- Each `.txt` file is one complete thread snapshot.
- Messages are ordered newest-first.
- Older messages are quoted with `|` or `>` prefixes.
- A dash separator (`----------------------------------------`) is optional.

### Canonical threads

In this dataset, a canonical thread is identified by the exact ordered Message-ID
sequence (`message_ids`).

Example:

```text
1_0_0.txt  = [<60aa...>, <33c9...>, <bd00...>]
1_0_0b.txt = [<60aa...>, <33c9...>, <bd00...>]  # same sequence
```

`1_0_0.txt` and `1_0_0b.txt` therefore belong to the same canonical thread. Body
and header formatting may differ (whitespace, disclaimer text, quote style,
header order), but Message-IDs match.

### Hierarchy

Let `message_ids` be the newest-first ordered Message-ID sequence for a document.

The parent of a non-root thread is the same sequence with the newest Message-ID
removed:

```text
parent_message_ids = message_ids[1:]
```

Example:

```text
1_0_0.message_ids = [<60aa...>, <33c9...>, <bd00...>]
1_0.message_ids   = [<33c9...>, <bd00...>]
1.message_ids     = [<bd00...>]

so: 1 → 1_0 → 1_0_0
```

The hierarchy is a tree, not only a linear chain. Branches such as `1_0` and
`1_1` are siblings under `1`.

### Eval filenames are gold labels only

Eval names encode ground truth for scoring only (`eval_labels.py`). Ingestion
must not use them.


| From filename                  | Gold field               |
| ------------------------------ | ------------------------ |
| strip trailing `b`/`c`/`d`/`e` | `canonical_label`        |
| drop last path segment         | `parent_label`           |
| number of path segments        | `expected_message_count` |


```text
1_0_0b.txt
  → canonical_label=1_0_0
  → parent_label=1_0
  → expected_message_count=3
```

Test files (`docXXXX.txt`) have opaque names and no labels.

### Parsing validation (`scripts/evaluate.py parsing`)

In-memory check against `data/eval` (no database):

1. Read each file, derive gold labels from the filename, parse content → `message_ids`.
2. Index parsed docs by `canonical_label`.
3. Score:
  - parse errors
  - `len(message_ids) == expected_message_count`
  - variants with the same gold label share the same `message_ids`
  - for each child: `child.message_ids[1:] == parent.message_ids`

```text
1_0_0.message_ids      = [60aa, 33c9, bd00]
1_0_0.message_ids[1:]  = [33c9, bd00]
1_0.message_ids        = [33c9, bd00]   # match
```

Run commands and output field meanings: [README.md — Validate parsing](README.md#validate-parsing).

### Dedup validation (`scripts/evaluate.py dedup`)

Score pairwise clustering after `canonical_id = sha256(join(message_ids, "\n"))`:


| Count             | Meaning                                      |
| ----------------- | -------------------------------------------- |
| `true_positives`  | Same gold label and same predicted canonical |
| `false_positives` | False merges: predicted same, gold different |
| `false_negatives` | False splits: gold same, predicted different |


`precision = TP/(TP+FP)`, `recall = TP/(TP+FN)`,
`f1 = 2 * precision * recall / (precision + recall)`.
`status=PASS` only when FP = FN = 0 (and no parse failures).

Why F1, not only accuracy / pass-fail: the assignment allows imperfect near-dedup.
Most doc pairs are true negatives (unrelated threads), so accuracy stays high even
when merges/splits are wrong. Pairwise precision/recall/F1 focus on the hard
“should these two be the same canonical?” cases and stay meaningful when the
score is below 100%.

### Hierarchy validation (`scripts/evaluate.py hierarchy`)

Link observed canonicals with:

```text
expected_parent_id = sha256(join(message_ids[1:], "\n"))  # None for roots. when len(message_ids) == 1
```

Create canonical nodes only for observed documents. Parent/children resolve at query time when the
matching parent id exists in the store, so child-first ingestion still works.

Score parent→child edges with TP/FP/FN (extra edge / missing edge). Also verify
`natural`, `reverse`, `child_first`, and `random` ingestion orders yield the same
final canonical set and edge set.

## Decisions

- A document’s `canonical_id` is the SHA-256 of its newest-first `message_ids`
sequence (joined with `"\n"`). Look that id up in the canonical store: if
present, map the document to it; if absent, insert a new canonical and map.

```text
canonical_id = sha256(join(message_ids, "\n"))

if canonical_id in store:
    map document_id → canonical_id
else:
    create canonical(canonical_id, message_ids)
    map document_id → canonical_id
```

- Each document keeps its own `document_id`. Only identical sequences share a
`canonical_id` (parent/child sequences do not):

```text
1_0_0.txt / 1_0_0b.txt / 1_0_0c.txt
  message_ids = [60aa, 33c9, bd00]
  → same canonical_id = sha256(join([60aa, 33c9, bd00], "\n"))

1_0   = [33c9, bd00]       → sha256(...)   # different sequence
1_0_0 = [60aa, 33c9, bd00] → sha256(...)   # parent/child, not the same
```

- Hierarchy uses observed-only nodes and `expected_parent_id = hash(message_ids[1:])`.
Unresolved parents stay pending until that canonical is observed.



## Tradeoffs

- Message-ID equality is simple and fits the supplied data, but it is not a
general near-dedup strategy if Message-IDs are missing or mutated.



## Assumptions

- Every parseable message has a usable Message-ID.
- Newest-first order is stable in both `eval` and `test`.
- Eval filename structure is trustworthy for scoring only.

