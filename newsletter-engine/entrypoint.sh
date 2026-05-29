#!/bin/bash
set -e

echo "Running database migrations..."
alembic -c /app/migrations/alembic.ini upgrade head
echo "Migrations complete."

exec uvicorn main:app --host 0.0.0.0 --port 8000
