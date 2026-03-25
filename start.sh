#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  . ".env"
  set +a
fi

PYTHON_BIN="${PROTEIN_BINDER_AGENT_RUNTIME_PYTHON:-python3}"
PID_FILE="${PROTEIN_BINDER_AGENT_PID_FILE:-$ROOT_DIR/protein-binder-agent.pid}"
LOG_DIR="${PROTEIN_BINDER_AGENT_LOG_DIR:-$ROOT_DIR/logs}"
HOST="${PROTEIN_BINDER_AGENT_API_HOST:-0.0.0.0}"
PORT="${PROTEIN_BINDER_AGENT_API_PORT:-8200}"
CONFIG_PATH="${PROTEIN_BINDER_AGENT_CONFIG:-protein_agent/config/agent_config.yaml}"
LOG_FILE="${LOG_DIR}/protein-binder-agent.log"

mkdir -p "$LOG_DIR"
mkdir -p "${PROTEIN_BINDER_AGENT_DATA_DIR:-$ROOT_DIR/data}"
mkdir -p "${PROTEIN_BINDER_AGENT_RESULT_DIR:-$ROOT_DIR/data/results}"
mkdir -p "${PROTEIN_BINDER_AGENT_ANALYSIS_DIR:-$ROOT_DIR/data/analysis}"
mkdir -p "${PROTEIN_BINDER_AGENT_UPLOAD_DIR:-$ROOT_DIR/data/uploads}"
mkdir -p "${PROTEIN_BINDER_AGENT_CONVERTED_STRUCTURES_DIR:-$ROOT_DIR/data/converted_structures}"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${OLD_PID}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "protein-binder-agent is already running with PID ${OLD_PID}"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

echo "Starting protein-binder-agent on ${HOST}:${PORT}"
nohup "$PYTHON_BIN" main.py serve --host "$HOST" --port "$PORT" --config "$CONFIG_PATH" >"$LOG_FILE" 2>&1 &
AGENT_PID=$!
echo "$AGENT_PID" >"$PID_FILE"
sleep 2

if kill -0 "$AGENT_PID" 2>/dev/null; then
  echo "protein-binder-agent started"
  echo "PID: $AGENT_PID"
  echo "Log: $LOG_FILE"
  echo "Health: http://127.0.0.1:${PORT}/health"
else
  echo "protein-binder-agent failed to start"
  echo "Last log lines:"
  tail -n 40 "$LOG_FILE" || true
  exit 1
fi
