from pathlib import Path

import pytest

from email_dedup.canonicalization import canonical_id_for
from email_dedup.hierarchy import CanonicalStore, expected_parent_id_for
from email_dedup.parser import parse_thread

EVAL_DIR = Path(__file__).resolve().parents[2] / "data" / "eval"


def _ids(name: str) -> tuple[str, ...]:
    return parse_thread((EVAL_DIR / name).read_text(encoding="utf-8")).message_ids


def test_root_has_no_expected_parent() -> None:
    assert expected_parent_id_for(_ids("1.txt")) is None


def test_expected_parent_id_matches_parent_canonical() -> None:
    parent_ids = _ids("1_0.txt")
    child_ids = _ids("1_0_0.txt")

    assert expected_parent_id_for(child_ids) == canonical_id_for(parent_ids)


def test_child_first_resolves_when_parent_arrives() -> None:
    store = CanonicalStore()
    child = store.upsert("1_0_0.txt", _ids("1_0_0.txt"))
    assert store.resolved_parent(child.canonical_id) is None

    parent = store.upsert("1_0.txt", _ids("1_0.txt"))
    assert store.resolved_parent(child.canonical_id) == parent.canonical_id
    assert child.canonical_id in store.children(parent.canonical_id)


def test_branching_parent_lists_all_children() -> None:
    store = CanonicalStore()
    root = store.upsert("1.txt", _ids("1.txt"))
    child_a = store.upsert("1_0.txt", _ids("1_0.txt"))
    child_b = store.upsert("1_1.txt", _ids("1_1.txt"))

    assert store.children(root.canonical_id) == frozenset(
        {child_a.canonical_id, child_b.canonical_id}
    )


def test_ingestion_order_does_not_change_final_edges() -> None:
    docs = [
        ("1.txt", _ids("1.txt")),
        ("1_0.txt", _ids("1_0.txt")),
        ("1_0_0.txt", _ids("1_0_0.txt")),
        ("1_0_0b.txt", _ids("1_0_0b.txt")),
        ("1_1.txt", _ids("1_1.txt")),
    ]

    def build(order: list[tuple[str, tuple[str, ...]]]) -> frozenset[tuple[str, str]]:
        store = CanonicalStore()
        for document_id, message_ids in order:
            store.upsert(document_id, message_ids)
        return store.resolved_edges()

    normal = build(docs)
    reversed_order = build(list(reversed(docs)))
    child_first = build(
        [
            ("1_0_0b.txt", _ids("1_0_0b.txt")),
            ("1_0_0.txt", _ids("1_0_0.txt")),
            ("1_1.txt", _ids("1_1.txt")),
            ("1_0.txt", _ids("1_0.txt")),
            ("1.txt", _ids("1.txt")),
        ]
    )

    assert normal == reversed_order == child_first
    assert len(normal) == 3  # 1→1_0, 1_0→1_0_0, 1→1_1


def test_variants_map_to_same_canonical_node() -> None:
    store = CanonicalStore()
    a = store.upsert("1_0_0.txt", _ids("1_0_0.txt"))
    b = store.upsert("1_0_0b.txt", _ids("1_0_0b.txt"))

    assert a.canonical_id == b.canonical_id
    assert store.documents_for(a.canonical_id) == frozenset({"1_0_0.txt", "1_0_0b.txt"})


def test_conflicting_document_content_raises() -> None:
    store = CanonicalStore()
    store.upsert("doc.txt", _ids("1.txt"))
    with pytest.raises(ValueError, match="different canonical"):
        store.upsert("doc.txt", _ids("1_0.txt"))
