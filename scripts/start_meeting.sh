#!/bin/bash
set -euo pipefail

echo "Checking prerequisites..."
command -v ffmpeg >/dev/null || { echo "Install FFmpeg: brew install ffmpeg"; exit 1; }
command -v ollama >/dev/null || { echo "Install Ollama: brew install ollama"; exit 1; }

echo "Starting Ollama..."
ollama serve >/tmp/parrot-script-ollama.log 2>&1 &
sleep 2

echo "Starting backend..."
cd "$(dirname "$0")/.."
PYTHON_BIN="python"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi
"$PYTHON_BIN" -m uvicorn backend.api.server:app --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8000}" --log-level "${API_LOG_LEVEL:-info}" >/tmp/parrot-script-backend.log 2>&1 &
sleep 2

echo ""
echo "Parrot Script is running"
echo "  API:      http://127.0.0.1:${API_PORT:-8000}"
echo "  Docs:     http://127.0.0.1:${API_PORT:-8000}/docs"
echo "  Frontend: http://127.0.0.1:5173"
echo ""
echo "Run frontend with: cd frontend && npm run dev"
