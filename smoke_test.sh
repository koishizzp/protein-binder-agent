#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  . ".env"
  set +a
fi

PORT="${PROTEIN_BINDER_AGENT_API_PORT:-8200}"
BASE_URL="http://127.0.0.1:${PORT}"

curl -fsS "${BASE_URL}/health"
echo
curl -fsS "${BASE_URL}/ui/status"
echo
curl -fsS "${BASE_URL}/v1/models"
echo
