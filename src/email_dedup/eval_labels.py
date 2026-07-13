"""Filename-derived ground truth helpers used only by evaluation code."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_VARIANT_SUFFIX = re.compile(r"[a-z]+$")


@dataclass(frozen=True, slots=True)
class EvalLabel:
    """Gold labels decoded from an eval filename."""

    document_id: str
    canonical_label: str
    parent_label: str | None
    expected_message_count: int


def normalize_eval_stem(stem: str) -> str:
    """Strip trailing variant letters from the last path segment."""
    parts = stem.split("_")
    parts[-1] = _VARIANT_SUFFIX.sub("", parts[-1])
    if not parts[-1]:
        raise ValueError(f"invalid eval stem after variant strip: {stem!r}")
    return "_".join(parts)


def eval_label_from_path(path: Path) -> EvalLabel:
    """Derive gold canonical/parent labels and expected message count."""
    stem = path.stem
    canonical_label = normalize_eval_stem(stem)
    parts = canonical_label.split("_")
    parent_label = "_".join(parts[:-1]) if len(parts) > 1 else None
    return EvalLabel(
        document_id=path.name,
        canonical_label=canonical_label,
        parent_label=parent_label,
        expected_message_count=len(parts),
    )
