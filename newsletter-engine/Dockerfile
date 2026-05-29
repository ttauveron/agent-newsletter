FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY newsletter-engine/pyproject.toml newsletter-engine/uv.lock ./
RUN uv sync --frozen --no-dev

COPY newsletter-engine/ /app/
COPY migrations/ /app/migrations/

RUN chmod +x /app/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"

CMD ["/app/entrypoint.sh"]
