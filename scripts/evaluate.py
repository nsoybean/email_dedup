"""Evaluate parsing, deduplication, and hierarchy against the eval corpus.

Filename structure is used only here. Application parsing and ingestion receive
document IDs and content only.
"""

from __future__ import annotations

import argparse
import itertools
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from email_dedup.canonicalization import canonical_id_for
from email_dedup.eval_labels import EvalLabel, eval_label_from_path
from email_dedup.hierarchy import CanonicalStore
from email_dedup.parser import ParseError, parse_thread


@dataclass(frozen=True, slots=True)
class ParsedEvalDocument:
    path: Path
    label: EvalLabel
    message_ids: tuple[str, ...]
    canonical_id: str


@dataclass
class ParsingReport:
    files_checked: int = 0
    parse_failures: list[str] = field(default_factory=list)
    count_mismatches: list[str] = field(default_factory=list)
    variant_sequence_mismatches: list[str] = field(default_factory=list)
    parent_sequence_mismatches: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.parse_failures
            or self.count_mismatches
            or self.variant_sequence_mismatches
            or self.parent_sequence_mismatches
        )


@dataclass
class DedupReport:
    files_checked: int = 0
    parse_failures: list[str] = field(default_factory=list)
    true_positives: int = 0
    false_positives: int = 0  # false merges: predicted same, gold different
    false_negatives: int = 0  # false splits: predicted different, gold same
    false_positive_pairs: list[str] = field(default_factory=list)
    false_negative_pairs: list[str] = field(default_factory=list)
    unique_predicted_canonicals: int = 0
    unique_gold_labels: int = 0

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        if denominator == 0:
            return 1.0
        return self.true_positives / denominator

    @property
    def recall(self) -> float:
        denominator = self.true_positives + self.false_negatives
        if denominator == 0:
            return 1.0
        return self.true_positives / denominator

    @property
    def f1(self) -> float:
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)

    @property
    def ok(self) -> bool:
        return (
            not self.parse_failures
            and self.false_positives == 0
            and self.false_negatives == 0
        )


@dataclass
class HierarchyReport:
    files_checked: int = 0
    parse_failures: list[str] = field(default_factory=list)
    order: str = "natural"
    seed: int | None = None
    true_positives: int = 0
    false_positives: int = 0  # extra predicted edges
    false_negatives: int = 0  # missing gold edges
    false_positive_edges: list[str] = field(default_factory=list)
    false_negative_edges: list[str] = field(default_factory=list)
    gold_edge_count: int = 0
    predicted_edge_count: int = 0
    order_independent: bool = True
    order_mismatches: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        if denominator == 0:
            return 1.0
        return self.true_positives / denominator

    @property
    def recall(self) -> float:
        denominator = self.true_positives + self.false_negatives
        if denominator == 0:
            return 1.0
        return self.true_positives / denominator

    @property
    def f1(self) -> float:
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)

    @property
    def ok(self) -> bool:
        return (
            not self.parse_failures
            and self.false_positives == 0
            and self.false_negatives == 0
            and self.order_independent
        )


def load_eval_documents(data_dir: Path) -> tuple[list[ParsedEvalDocument], list[str]]:
    documents: list[ParsedEvalDocument] = []
    failures: list[str] = []
    for path in sorted(data_dir.glob("*.txt")):
        label = eval_label_from_path(path)
        try:
            thread = parse_thread(path.read_text(encoding="utf-8"))
            canonical_id = canonical_id_for(thread.message_ids)
        except (ParseError, ValueError) as exc:
            failures.append(f"{path.name}: {exc}")
            continue
        documents.append(
            ParsedEvalDocument(
                path=path,
                label=label,
                message_ids=thread.message_ids,
                canonical_id=canonical_id,
            )
        )
    return documents, failures


def validate_parsing(data_dir: Path) -> ParsingReport:
    documents, failures = load_eval_documents(data_dir)
    report = ParsingReport(files_checked=len(documents) + len(failures), parse_failures=failures)

    by_canonical: dict[str, list[ParsedEvalDocument]] = defaultdict(list)
    for document in documents:
        by_canonical[document.label.canonical_label].append(document)
        if len(document.message_ids) != document.label.expected_message_count:
            report.count_mismatches.append(
                f"{document.path.name}: expected {document.label.expected_message_count} "
                f"messages, got {len(document.message_ids)}"
            )

    for label, group in sorted(by_canonical.items()):
        sequences = {doc.message_ids for doc in group}
        if len(sequences) > 1:
            rendered = ", ".join(
                f"{doc.path.name}={list(doc.message_ids)}" for doc in group
            )
            report.variant_sequence_mismatches.append(
                f"{label}: variants disagree on Message-ID sequence ({rendered})"
            )

    for document in documents:
        parent_label = document.label.parent_label
        if parent_label is None:
            continue
        parents = by_canonical.get(parent_label)
        if not parents:
            report.parent_sequence_mismatches.append(
                f"{document.path.name}: missing parsed parent {parent_label}"
            )
            continue
        parent_ids = parents[0].message_ids
        child_without_newest = document.message_ids[1:]
        if child_without_newest != parent_ids:
            report.parent_sequence_mismatches.append(
                f"{document.path.name}: message_ids[1:]={list(child_without_newest)} "
                f"!= parent {parent_label}={list(parent_ids)}"
            )

    return report


def validate_dedup(data_dir: Path) -> DedupReport:
    documents, failures = load_eval_documents(data_dir)
    report = DedupReport(
        files_checked=len(documents) + len(failures),
        parse_failures=failures,
        unique_predicted_canonicals=len({doc.canonical_id for doc in documents}),
        unique_gold_labels=len({doc.label.canonical_label for doc in documents}),
    )

    for left, right in itertools.combinations(documents, 2):
        gold_same = left.label.canonical_label == right.label.canonical_label
        pred_same = left.canonical_id == right.canonical_id
        pair = f"{left.path.name},{right.path.name}"

        if gold_same and pred_same:
            report.true_positives += 1
        elif pred_same and not gold_same:
            report.false_positives += 1
            report.false_positive_pairs.append(
                f"{pair}: false_positive(false_merge) "
                f"gold=({left.label.canonical_label},{right.label.canonical_label}) "
                f"pred={left.canonical_id[:12]}"
            )
        elif gold_same and not pred_same:
            report.false_negatives += 1
            report.false_negative_pairs.append(
                f"{pair}: false_negative(false_split) "
                f"gold={left.label.canonical_label} "
                f"pred=({left.canonical_id[:12]},{right.canonical_id[:12]})"
            )

    return report


def _order_documents(
    documents: list[ParsedEvalDocument],
    order: str,
    seed: int,
) -> list[ParsedEvalDocument]:
    docs = list(documents)
    if order == "natural":
        return docs
    if order == "reverse":
        return list(reversed(docs))
    if order == "child_first":
        return sorted(docs, key=lambda doc: (-len(doc.message_ids), doc.path.name))
    if order == "random":
        rng = random.Random(seed)
        rng.shuffle(docs)
        return docs
    raise ValueError(f"unsupported order: {order}")


def _build_store(documents: list[ParsedEvalDocument]) -> CanonicalStore:
    store = CanonicalStore()
    for document in documents:
        store.upsert(document.path.name, document.message_ids)
    return store


def _gold_edges(
    documents: list[ParsedEvalDocument],
) -> tuple[frozenset[tuple[str, str]], dict[str, str]]:
    by_label: dict[str, ParsedEvalDocument] = {}
    for document in documents:
        by_label.setdefault(document.label.canonical_label, document)

    label_to_canonical = {
        label: document.canonical_id for label, document in by_label.items()
    }
    edges: set[tuple[str, str]] = set()
    for label, document in by_label.items():
        parent_label = document.label.parent_label
        if parent_label is None:
            continue
        parent_canonical = label_to_canonical.get(parent_label)
        if parent_canonical is None:
            continue
        edges.add((parent_canonical, label_to_canonical[label]))
    return frozenset(edges), label_to_canonical


def validate_hierarchy(
    data_dir: Path,
    order: str = "natural",
    seed: int = 1,
) -> HierarchyReport:
    documents, failures = load_eval_documents(data_dir)
    report = HierarchyReport(
        files_checked=len(documents) + len(failures),
        parse_failures=failures,
        order=order,
        seed=seed if order == "random" else None,
    )
    if failures:
        return report

    gold_edges, label_to_canonical = _gold_edges(documents)
    canonical_to_label = {canonical_id: label for label, canonical_id in label_to_canonical.items()}
    ordered = _order_documents(documents, order, seed)
    store = _build_store(ordered)
    predicted_edges = store.resolved_edges()

    def _edge_label(edge: tuple[str, str]) -> str:
        parent, child = edge
        parent_label = canonical_to_label.get(parent, parent[:12])
        child_label = canonical_to_label.get(child, child[:12])
        return f"{parent_label}->{child_label}"

    report.gold_edge_count = len(gold_edges)
    report.predicted_edge_count = len(predicted_edges)
    report.true_positives = len(gold_edges & predicted_edges)
    false_pos = predicted_edges - gold_edges
    false_neg = gold_edges - predicted_edges
    report.false_positives = len(false_pos)
    report.false_negatives = len(false_neg)
    report.false_positive_edges = sorted(_edge_label(edge) for edge in false_pos)
    report.false_negative_edges = sorted(_edge_label(edge) for edge in false_neg)

    baseline_ids = store.canonical_ids
    baseline_edges = predicted_edges
    for other_order in ("natural", "reverse", "child_first", "random"):
        other_docs = _order_documents(documents, other_order, seed)
        other_store = _build_store(other_docs)
        if (
            other_store.canonical_ids != baseline_ids
            or other_store.resolved_edges() != baseline_edges
        ):
            report.order_independent = False
            report.order_mismatches.append(
                f"{other_order}: canonicals/edges differ from {order}"
            )

    return report


def _print_banner(title: str) -> None:
    print(f"=== {title} ===")


def _print_parsing_report(report: ParsingReport) -> None:
    _print_banner("parsing")
    print(f"files_checked={report.files_checked}")
    print(f"parse_failures={len(report.parse_failures)}")
    print(f"count_mismatches={len(report.count_mismatches)}")
    print(f"variant_sequence_mismatches={len(report.variant_sequence_mismatches)}")
    print(f"parent_sequence_mismatches={len(report.parent_sequence_mismatches)}")
    for section_name in (
        "parse_failures",
        "count_mismatches",
        "variant_sequence_mismatches",
        "parent_sequence_mismatches",
    ):
        for item in getattr(report, section_name):
            print(f"  [{section_name}] {item}")
    print("status=PASS" if report.ok else "status=FAIL")


def _print_dedup_report(report: DedupReport) -> None:
    _print_banner("dedup")
    print(f"files_checked={report.files_checked}")
    print(f"parse_failures={len(report.parse_failures)}")
    print(f"unique_gold_labels={report.unique_gold_labels}")
    print(f"unique_predicted_canonicals={report.unique_predicted_canonicals}")
    print(f"true_positives={report.true_positives}")
    print(f"false_positives={report.false_positives}  # false merges")
    print(f"false_negatives={report.false_negatives}  # false splits")
    print(f"precision={report.precision:.4f}")
    print(f"recall={report.recall:.4f}")
    print(f"f1={report.f1:.4f}")
    for item in report.parse_failures:
        print(f"  [parse_failures] {item}")
    for item in report.false_positive_pairs:
        print(f"  [false_positives] {item}")
    for item in report.false_negative_pairs:
        print(f"  [false_negatives] {item}")
    print("status=PASS" if report.ok else "status=FAIL")


def _print_hierarchy_report(report: HierarchyReport) -> None:
    title = f"hierarchy order={report.order}"
    if report.seed is not None and report.order == "random":
        title = f"{title} seed={report.seed}"
    _print_banner(title)
    print(f"files_checked={report.files_checked}")
    print(f"parse_failures={len(report.parse_failures)}")
    print(f"order={report.order}")
    if report.seed is not None:
        print(f"seed={report.seed}")
    print(f"gold_edge_count={report.gold_edge_count}")
    print(f"predicted_edge_count={report.predicted_edge_count}")
    print(f"true_positives={report.true_positives}")
    print(f"false_positives={report.false_positives}  # extra edges")
    print(f"false_negatives={report.false_negatives}  # missing edges")
    print(f"precision={report.precision:.4f}")
    print(f"recall={report.recall:.4f}")
    print(f"f1={report.f1:.4f}")
    print(f"order_independent={report.order_independent}")
    for item in report.parse_failures:
        print(f"  [parse_failures] {item}")
    for item in report.false_positive_edges:
        print(f"  [false_positives] {item}")
    for item in report.false_negative_edges:
        print(f"  [false_negatives] {item}")
    for item in report.order_mismatches:
        print(f"  [order_mismatches] {item}")
    print("status=PASS" if report.ok else "status=FAIL")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("parsing", "dedup", "hierarchy"),
        help="validation stage to run",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/eval"),
        help="directory of eval .txt files",
    )
    parser.add_argument(
        "--order",
        choices=("natural", "reverse", "child_first", "random"),
        default="natural",
        help="ingestion order for hierarchy validation",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=1,
        help="RNG seed used when --order=random",
    )
    args = parser.parse_args(argv)

    if args.mode == "parsing":
        report = validate_parsing(args.data_dir)
        _print_parsing_report(report)
        return 0 if report.ok else 1

    if args.mode == "dedup":
        report = validate_dedup(args.data_dir)
        _print_dedup_report(report)
        return 0 if report.ok else 1

    if args.mode == "hierarchy":
        report = validate_hierarchy(args.data_dir, order=args.order, seed=args.seed)
        _print_hierarchy_report(report)
        return 0 if report.ok else 1

    raise SystemExit(f"unsupported mode: {args.mode}")


if __name__ == "__main__":
    sys.exit(main())
