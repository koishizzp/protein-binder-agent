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

if [[ ! -f "$PID_FILE" ]]; then
  echo "No PID file found"
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -z "$PID" ]]; then
  echo "PID file is empty"
  rm -f "$PID_FILE"
  exit 0
fi

if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  for _ in {1..20}; do
    if ! kill -0 "$PID" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  if kill -0 "$PID" 2>/dev/null; then
    echo "Process did not exit after SIGTERM, sending SIGKILL"
    kill -9 "$PID"
  fi
  echo "Stopped protein-binder-agent (PID $PID)"
else
  echo "Process $PID is not running"
fi

rm -f "$PID_FILE"
