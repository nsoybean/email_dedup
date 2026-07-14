"""Order-independent canonical hierarchy via expected parent IDs."""

from __future__ import annotations

from dataclasses import dataclass, field

from email_dedup.canonicalization import assign_canonical, canonical_id_for
from email_dedup.models import CanonicalAssignment


def expected_parent_id_for(message_ids: tuple[str, ...] | list[str]) -> str | None:
    """Parent canonical id = hash of message_ids without the newest id."""
    ids = tuple(message_ids)
    if not ids:
        raise ValueError("message_ids must not be empty")
    if len(ids) == 1:
        return None
    return canonical_id_for(ids[1:])


def assign_with_parent(
    document_id: str,
    message_ids: tuple[str, ...] | list[str],
) -> CanonicalAssignment:
    """Assign canonical id and deterministic expected parent id."""
    ids = tuple(message_ids)
    assignment = assign_canonical(document_id, ids)
    return CanonicalAssignment(
        document_id=assignment.document_id,
        canonical_id=assignment.canonical_id,
        message_ids=assignment.message_ids,
        expected_parent_id=expected_parent_id_for(ids),
    )


@dataclass
class CanonicalNode:
    """An observed canonical thread (created only when a raw document arrives)."""

    canonical_id: str
    message_ids: tuple[str, ...]
    expected_parent_id: str | None
    document_ids: set[str] = field(default_factory=set)


@dataclass
class CanonicalStore:
    """In-memory observed-only canonical store with order-independent relations."""

    _nodes: dict[str, CanonicalNode] = field(default_factory=dict)
    _documents: dict[str, str] = field(default_factory=dict)  # document_id -> canonical_id

    def upsert(
        self,
        document_id: str,
        message_ids: tuple[str, ...] | list[str],
    ) -> CanonicalAssignment:
        assignment = assign_with_parent(document_id, message_ids)
        existing_canonical = self._documents.get(document_id)
        if existing_canonical is not None and existing_canonical != assignment.canonical_id:
            raise ValueError(
                f"document_id {document_id!r} already mapped to a different canonical"
            )

        node = self._nodes.get(assignment.canonical_id)
        if node is None:
            node = CanonicalNode(
                canonical_id=assignment.canonical_id,
                message_ids=assignment.message_ids,
                expected_parent_id=assignment.expected_parent_id,
            )
            self._nodes[assignment.canonical_id] = node
        elif node.message_ids != assignment.message_ids:
            raise ValueError(
                f"canonical {assignment.canonical_id} collision with different message_ids"
            )

        node.document_ids.add(document_id)
        self._documents[document_id] = assignment.canonical_id
        return assignment

    def get(self, canonical_id: str) -> CanonicalNode | None:
        return self._nodes.get(canonical_id)

    def canonical_for_document(self, document_id: str) -> str | None:
        return self._documents.get(document_id)

    def documents_for(self, canonical_id: str) -> frozenset[str]:
        node = self._nodes.get(canonical_id)
        if node is None:
            return frozenset()
        return frozenset(node.document_ids)

    def resolved_parent(self, canonical_id: str) -> str | None:
        """Return parent id only if that parent canonical has been observed."""
        node = self._nodes.get(canonical_id)
        if node is None or node.expected_parent_id is None:
            return None
        if node.expected_parent_id not in self._nodes:
            return None
        return node.expected_parent_id

    def children(self, canonical_id: str) -> frozenset[str]:
        """Observed children whose expected_parent_id equals this canonical."""
        return frozenset(
            node.canonical_id
            for node in self._nodes.values()
            if node.expected_parent_id == canonical_id
        )

    def resolved_edges(self) -> frozenset[tuple[str, str]]:
        """Parent→child edges where both ends are observed."""
        edges: set[tuple[str, str]] = set()
        for node in self._nodes.values():
            parent_id = self.resolved_parent(node.canonical_id)
            if parent_id is not None:
                edges.add((parent_id, node.canonical_id))
        return frozenset(edges)

    @property
    def canonical_ids(self) -> frozenset[str]:
        return frozenset(self._nodes)
