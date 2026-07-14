from pathlib import Path

import pytest

from email_dedup.canonicalization import assign_canonical, canonical_id_for, encode_message_ids
from email_dedup.parser import parse_thread

EVAL_DIR = Path(__file__).resolve().parents[2] / "data" / "eval"


def test_canonical_id_is_deterministic() -> None:
    message_ids = ("<a@example.com>", "<b@example.com>")

    assert canonical_id_for(message_ids) == canonical_id_for(list(message_ids))


def test_encoding_joins_with_newlines() -> None:
    assert encode_message_ids(("<a@x>", "<b@x>")) == "<a@x>\n<b@x>"


def test_distinct_sequences_get_distinct_ids() -> None:
    parent = ("<33c9@example.com>", "<bd00@example.com>")
    child = ("<60aa@example.com>", "<33c9@example.com>", "<bd00@example.com>")

    assert canonical_id_for(parent) != canonical_id_for(child)


def test_exact_duplicates_share_canonical_id() -> None:
    message_ids = ("<one@example.com>",)
    first = assign_canonical("doc1.txt", message_ids)
    second = assign_canonical("doc2.txt", message_ids)

    assert first.canonical_id == second.canonical_id
    assert first.document_id != second.document_id


def test_eval_variants_share_canonical_id() -> None:
    base = parse_thread((EVAL_DIR / "1_0_0.txt").read_text(encoding="utf-8"))
    variant = parse_thread((EVAL_DIR / "1_0_0b.txt").read_text(encoding="utf-8"))

    assert assign_canonical("1_0_0.txt", base.message_ids).canonical_id == assign_canonical(
        "1_0_0b.txt", variant.message_ids
    ).canonical_id


def test_parent_and_child_have_different_canonical_ids() -> None:
    parent = parse_thread((EVAL_DIR / "1_0.txt").read_text(encoding="utf-8"))
    child = parse_thread((EVAL_DIR / "1_0_0.txt").read_text(encoding="utf-8"))

    assert canonical_id_for(parent.message_ids) != canonical_id_for(child.message_ids)


def test_empty_message_ids_raise() -> None:
    with pytest.raises(ValueError, match="empty"):
        canonical_id_for(())


def test_blank_message_id_raises() -> None:
    with pytest.raises(ValueError, match="blank"):
        canonical_id_for(("<ok@example.com>", "  "))
