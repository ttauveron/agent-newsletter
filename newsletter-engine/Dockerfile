FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY newsletter-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY newsletter-engine/ /app/
COPY migrations/ /app/migrations/

RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
