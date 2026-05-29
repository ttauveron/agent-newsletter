FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY newsletter-engine/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY newsletter-engine/ /app/
COPY migrations/ /app/migrations/

RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
