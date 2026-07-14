# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install deps first for better layer caching
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY data ./data

ENV PYTHONUNBUFFERED=1
ENV EMAIL_DEDUP_ENV=production

# Default process is the API; Compose overrides for migrate/worker.
EXPOSE 8000
CMD ["uvicorn", "email_dedup.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
