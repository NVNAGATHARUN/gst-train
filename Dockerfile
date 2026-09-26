FROM ghcr.io/astral-sh/uv:0.8.22 AS uv

FROM python:3.12.11-slim-bookworm AS builder
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12.11-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/backend \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --system railsync && useradd --system --gid railsync --home-dir /app railsync
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY backend ./backend
USER railsync
EXPOSE 8000
CMD ["uvicorn", "railsync.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
