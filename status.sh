#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  . ".env"
  set +a
fi

PID_FILE="${PROTEIN_BINDER_AGENT_PID_FILE:-$ROOT_DIR/protein-binder-agent.pid}"
PORT="${PROTEIN_BINDER_AGENT_API_PORT:-8200}"
LOG_DIR="${PROTEIN_BINDER_AGENT_LOG_DIR:-$ROOT_DIR/logs}"
LOG_FILE="${LOG_DIR}/protein-binder-agent.log"

echo "Protein Binder Agent status"
echo "Repository: $ROOT_DIR"
echo "Port: $PORT"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "Process: running (PID $PID)"
  else
    echo "Process: stale PID file ($PID)"
  fi
else
  echo "Process: not running"
fi

if command -v curl >/dev/null 2>&1; then
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo "Health: ok"
  else
    echo "Health: unavailable"
  fi
else
  echo "Health: curl not installed"
fi

if [[ -f "$LOG_FILE" ]]; then
  echo "Log: $LOG_FILE"
else
  echo "Log: not created yet"
fi
