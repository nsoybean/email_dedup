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
