#!/bin/bash
# One-time setup: generate LiteLLM virtual keys for hermes and newsletter-engine.
# Run after: docker compose up litellm
#
# Usage: LITELLM_MASTER_KEY=sk-... scripts/litellm-init-keys.sh
#
# Copy the output lines into your .env file.

set -euo pipefail

LITELLM_URL="${LITELLM_URL:-http://localhost:4000}"
MASTER_KEY="${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY is required}"

generate_key() {
  local alias="$1"
  local model="$2"

  curl -sf -X POST "$LITELLM_URL/key/generate" \
    -H "Authorization: Bearer $MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"models\": [\"$model\"], \"key_alias\": \"$alias\"}" \
    | grep -o '"key":"[^"]*"' \
    | cut -d'"' -f4
}

echo "Generating virtual keys against $LITELLM_URL ..."

HERMES_KEY=$(generate_key "hermes-agent" "hermes")
ENRICHMENT_KEY=$(generate_key "newsletter-engine-enrichment" "enrichment")

echo ""
echo "Add these lines to your .env:"
echo ""
echo "LITELLM_HERMES_KEY=$HERMES_KEY"
echo "LITELLM_ENRICHMENT_KEY=$ENRICHMENT_KEY"
