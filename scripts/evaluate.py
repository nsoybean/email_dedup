"""Evaluate parsing, deduplication, and hierarchy against the eval corpus.

Filename structure is used only here. Application parsing and ingestion receive
document IDs and content only.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from email_dedup.eval_labels import EvalLabel, eval_label_from_path
from email_dedup.parser import ParseError, parse_thread


@dataclass(frozen=True, slots=True)
class ParsedEvalDocument:
    path: Path
    label: EvalLabel
    message_ids: tuple[str, ...]


@dataclass
class ParsingReport:
    files_checked: int = 0
    parse_failures: list[str] | None = None
    count_mismatches: list[str] | None = None
    variant_sequence_mismatches: list[str] | None = None
    parent_sequence_mismatches: list[str] | None = None

    def __post_init__(self) -> None:
        self.parse_failures = self.parse_failures or []
        self.count_mismatches = self.count_mismatches or []
        self.variant_sequence_mismatches = self.variant_sequence_mismatches or []
        self.parent_sequence_mismatches = self.parent_sequence_mismatches or []

    @property
    def ok(self) -> bool:
        return not (
            self.parse_failures
            or self.count_mismatches
            or self.variant_sequence_mismatches
            or self.parent_sequence_mismatches
        )


def load_eval_documents(data_dir: Path) -> tuple[list[ParsedEvalDocument], list[str]]:
    documents: list[ParsedEvalDocument] = []
    failures: list[str] = []
    for path in sorted(data_dir.glob("*.txt")):
        label = eval_label_from_path(path)
        try:
            thread = parse_thread(path.read_text(encoding="utf-8"))
        except ParseError as exc:
            failures.append(f"{path.name}: {exc}")
            continue
        documents.append(
            ParsedEvalDocument(path=path, label=label, message_ids=thread.message_ids)
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


def _print_parsing_report(report: ParsingReport) -> None:
    print(f"files_checked={report.files_checked}")
    print(f"parse_failures={len(report.parse_failures or [])}")
    print(f"count_mismatches={len(report.count_mismatches or [])}")
    print(f"variant_sequence_mismatches={len(report.variant_sequence_mismatches or [])}")
    print(f"parent_sequence_mismatches={len(report.parent_sequence_mismatches or [])}")
    for section_name in (
        "parse_failures",
        "count_mismatches",
        "variant_sequence_mismatches",
        "parent_sequence_mismatches",
    ):
        items = getattr(report, section_name) or []
        for item in items:
            print(f"  [{section_name}] {item}")
    print("status=PASS" if report.ok else "status=FAIL")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("parsing",),
        help="validation stage to run",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/eval"),
        help="directory of eval .txt files",
    )
    args = parser.parse_args(argv)

    if args.mode == "parsing":
        report = validate_parsing(args.data_dir)
        _print_parsing_report(report)
        return 0 if report.ok else 1

    raise SystemExit(f"unsupported mode: {args.mode}")


if __name__ == "__main__":
    sys.exit(main())
