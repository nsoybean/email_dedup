"""Application settings loaded from environment variables."""

import os
from dataclasses import dataclass

DEFAULT_ENVIRONMENT = "development"
DEFAULT_LOG_LEVEL = "INFO"


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings shared by future API and worker processes."""

    environment: str = DEFAULT_ENVIRONMENT
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_environment(cls) -> "Settings":
        """Create settings without coupling domain code to a framework."""
        return cls(
            environment=os.getenv("EMAIL_DEDUP_ENV", DEFAULT_ENVIRONMENT),
            log_level=os.getenv("EMAIL_DEDUP_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        )
