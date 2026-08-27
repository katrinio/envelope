# Envelope: FastAPI + server-rendered UI

# ============================================================================
# builder: Build Python wheel and install into a virtual environment
# ============================================================================

FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install --no-cache-dir "poetry>=2.0,<3.0"

COPY pyproject.toml poetry.lock README.md ./
COPY src ./src

RUN poetry build --format wheel \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir dist/python_project_template-*.whl

# ============================================================================
# runtime: Minimal production image
# ============================================================================

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    DATABASE_URL="sqlite:////data/envelope.db"

WORKDIR /app

RUN apt-get update && \
    apt-get install --yes --no-install-recommends \
        ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Copy Python runtime from builder
COPY --from=builder /opt/venv /opt/venv

# Copy migration files
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

RUN useradd \
        --create-home \
        --uid 10001 \
        --shell /usr/sbin/nologin \
        envelope && \
    mkdir -p /data && \
    chown -R envelope:envelope /app /data /opt/venv

USER envelope

EXPOSE 8000

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --retries=3 \
    --start-period=10s \
    CMD curl --fail --silent http://127.0.0.1:8000/docs >/dev/null || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
