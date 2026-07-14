"""Application settings loaded from environment variables."""

import os
from dataclasses import dataclass

DEFAULT_ENVIRONMENT = "development"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_DATABASE_URL = "postgresql+psycopg://email:email@localhost:5433/email_dedup"
DEFAULT_WORKER_POLL_INTERVAL_SECONDS = 0.5
DEFAULT_WORKER_MAX_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings shared by API and worker processes."""

    environment: str = DEFAULT_ENVIRONMENT
    log_level: str = DEFAULT_LOG_LEVEL
    database_url: str = DEFAULT_DATABASE_URL
    worker_poll_interval_seconds: float = DEFAULT_WORKER_POLL_INTERVAL_SECONDS
    worker_max_attempts: int = DEFAULT_WORKER_MAX_ATTEMPTS

    @classmethod
    def from_environment(cls) -> "Settings":
        """Create settings without coupling domain code to a framework."""
        return cls(
            environment=os.getenv("EMAIL_DEDUP_ENV", DEFAULT_ENVIRONMENT),
            log_level=os.getenv("EMAIL_DEDUP_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            worker_poll_interval_seconds=float(
                os.getenv(
                    "WORKER_POLL_INTERVAL_SECONDS",
                    str(DEFAULT_WORKER_POLL_INTERVAL_SECONDS),
                )
            ),
            worker_max_attempts=int(
                os.getenv("WORKER_MAX_ATTEMPTS", str(DEFAULT_WORKER_MAX_ATTEMPTS))
            ),
        )
