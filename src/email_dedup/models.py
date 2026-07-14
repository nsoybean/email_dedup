from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawDocument:
    """A raw email-thread snapshot (newest-first) submitted for ingestion."""

    document_id: str
    content: str

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id must not be blank")
        if not self.content.strip():
            raise ValueError("content must not be blank")


@dataclass(frozen=True, slots=True)
class ParsedMessage:
    """One email message extracted from a thread snapshot."""

    message_id: str
    headers: dict[str, str]
    body: str


@dataclass(frozen=True, slots=True)
class ParsedThread:
    """A newest-first thread snapshot with an ordered Message-ID sequence."""

    messages: tuple[ParsedMessage, ...]

    @property
    def message_ids(self) -> tuple[str, ...]:
        return tuple(message.message_id for message in self.messages)


@dataclass(frozen=True, slots=True)
class CanonicalAssignment:
    """Mapping from a raw document to its deterministic canonical thread."""

    document_id: str
    canonical_id: str
    message_ids: tuple[str, ...]
    expected_parent_id: str | None = None
