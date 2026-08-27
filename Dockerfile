#   Envelope: Python-only production image
#   FastAPI + Jinja2 on :8000
#   Database: SQLite under /data
#   User: postbox (non-root)

# ============================================================================
# builder: Build Python wheel and install into a virtual environment
# ============================================================================

FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN apt-get update && \
    apt-get install --yes --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry>=2.0,<3.0"

COPY pyproject.toml poetry.lock README.md ./
COPY src ./src

RUN poetry build --format wheel && \
    wheel_file=$(ls dist/postbox-*.whl | head -1) && \
    test -n "$wheel_file" || (echo "ERROR: No wheel produced"; exit 1)

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir dist/postbox-*.whl

RUN cd /tmp && \
    /opt/venv/bin/python -c "import postbox; import postbox.api; assert '/opt/venv' in postbox.__file__, postbox.__file__" && \
    test -x /opt/venv/bin/postbox-api

# Verify templates and static assets are packaged
RUN /opt/venv/bin/python -c "\
from pathlib import Path; import postbox; \
pkg = Path(postbox.__file__).parent; \
assert (pkg / 'templates' / 'base.html').exists(), 'missing templates'; \
assert (pkg / 'static' / 'css' / 'app.css').exists(), 'missing static assets'; \
"

# ============================================================================
# runtime: Minimal production image
# ============================================================================

FROM python:3.14-slim AS runtime

# Build argument for version (e.g., git SHA or release tag)
# Pass via: docker build --build-arg VERSION=<git-sha>
ARG VERSION=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    POSTBOX_STATIC_VERSION="${VERSION}"

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

# Create application user and data directory
RUN useradd \
        --create-home \
        --uid 10001 \
        --shell /usr/sbin/nologin \
        postbox && \
    mkdir -p /data && \
    chown -R postbox:postbox /app /data /opt/venv

# Smoke check: verify runtime
RUN command -v postbox-api && \
    python -c "import postbox"

USER postbox

EXPOSE 8000

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --retries=3 \
    --start-period=10s \
    CMD curl --fail --silent http://127.0.0.1:8000/api/ready || exit 1

CMD ["postbox-api"]
