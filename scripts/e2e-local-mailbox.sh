#!/usr/bin/env bash
set -euo pipefail

project="agent-newsletter-e2e"
api="http://127.0.0.1:18000"

export POSTGRES_DB="${POSTGRES_DB:-hermes_db}"
export POSTGRES_SUPERUSER="${POSTGRES_SUPERUSER:-postgres}"
export POSTGRES_SUPERUSER_PASSWORD="${POSTGRES_SUPERUSER_PASSWORD:-e2e_superuser}"
export NEWSLETTER_ENGINE_DB_USER="${NEWSLETTER_ENGINE_DB_USER:-newsletter_engine}"
export NEWSLETTER_ENGINE_DB_PASSWORD="${NEWSLETTER_ENGINE_DB_PASSWORD:-e2e_newsletter}"
export HERMES_DB_USER="${HERMES_DB_USER:-hermes_readonly}"
export HERMES_DB_PASSWORD="${HERMES_DB_PASSWORD:-e2e_hermes}"
export HERMES_API_KEY="${HERMES_API_KEY:-e2e_hermes_api_key}"
export NEWSLETTER_ENGINE_PORT=18000

compose=(docker compose -p "$project" -f docker-compose.yml -f docker-compose.e2e.yml)

cleanup() {
  "${compose[@]}" down -v >/dev/null
}

trap cleanup EXIT

"${compose[@]}" up -d --build postgres newsletter-engine

for _ in $(seq 1 30); do
  if curl -fs "$api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS "$api/health" >/dev/null

curl -fsS -X POST "$api/dev/emails" \
  -H "Content-Type: application/json" \
  -d '{"message_id":"newsletter-1","sender_email":"newsletter@example.com","subject":"Security Weekly","body":"IAM and cloud security update."}' \
  >/dev/null

curl -fsS -X POST "$api/dev/emails" \
  -H "Content-Type: application/json" \
  -d '{"message_id":"user-1","sender_email":"user@example.com","subject":"Question","body":"What happened this week?"}' \
  >/dev/null

curl -fsS -X POST "$api/trigger/poll" >/dev/null

newsletter_count=$("${compose[@]}" exec -T postgres psql \
  -U "$POSTGRES_SUPERUSER" \
  -d "$POSTGRES_DB" \
  -tAc "select count(*) from emails where gmail_message_id = 'newsletter-1' and processing_state in ('cleaned', 'ready_for_hermes')")

user_message_id=$("${compose[@]}" exec -T postgres psql \
  -U "$POSTGRES_SUPERUSER" \
  -d "$POSTGRES_DB" \
  -tAc "select id from user_messages where gmail_message_id = 'user-1' and processing_state = 'user_message_received' limit 1")

if [[ "$newsletter_count" != "1" ]]; then
  echo "Expected newsletter-1 to be ingested, got count=$newsletter_count" >&2
  exit 1
fi

if [[ -z "$user_message_id" ]]; then
  echo "Expected user-1 to be stored as a user message" >&2
  exit 1
fi

curl -fsS -X POST "$api/actions/send-reply" \
  -H "Content-Type: application/json" \
  -d "{\"user_message_id\":\"$user_message_id\",\"content\":\"Local e2e reply.\"}" \
  >/dev/null

outbox=$(curl -fsS "$api/dev/outbox")
if [[ "$outbox" != *"Local e2e reply."* ]]; then
  echo "Expected local outbox to contain the reply" >&2
  exit 1
fi

echo "Local mailbox e2e scenario passed."
