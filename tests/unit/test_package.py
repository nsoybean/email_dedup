from dataclasses import FrozenInstanceError

import pytest

from email_dedup import RawDocument, Settings


def test_package_exports_domain_types() -> None:
    document = RawDocument(document_id="doc1.txt", content="Message-ID: <one@example.com>")

    assert document.document_id == "doc1.txt"
    assert Settings().environment == "development"


def test_raw_document_is_immutable() -> None:
    document = RawDocument(document_id="doc1.txt", content="Message-ID: <one@example.com>")

    with pytest.raises(FrozenInstanceError):
        document.document_id = "doc2.txt"  # type: ignore[misc]


def test_settings_are_loaded_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_DEDUP_ENV", "test")
    monkeypatch.setenv("EMAIL_DEDUP_LOG_LEVEL", "debug")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@localhost:5432/z")

    settings = Settings.from_environment()

    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.database_url.endswith("/z")
