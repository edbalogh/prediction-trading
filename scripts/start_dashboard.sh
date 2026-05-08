#!/usr/bin/env bash
# Starts the nautilus-plus dashboard.
# Usage: bash scripts/start_dashboard.sh [--dev]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR/.."
UI_DIR="$ROOT/dashboard/ui"

if [[ "$1" == "--dev" ]]; then
  echo "Starting in development mode (hot reload)..."
  # Start FastAPI in background
  uvicorn dashboard.api.main:app --reload --port 8000 &
  API_PID=$!
  # Start Vite dev server
  cd "$UI_DIR" && npm run dev
  kill "$API_PID"
else
  echo "Building UI..."
  cd "$UI_DIR" && npm run build
  echo "Starting dashboard at http://0.0.0.0:8000"
  cd "$ROOT" && uvicorn dashboard.api.main:app --host 0.0.0.0 --port 8000
fi
