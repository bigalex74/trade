#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-/home/user/trading_venv/bin/python}"
LOCK_FILE="${AI_MEMORY_INDEXER_LOCK_FILE:-/tmp/ai_memory_indexer.lock}"
SCRIPT="${PROJECT_DIR}/ai_memory_indexer.py"

if [ -f "/home/user/.env.trading" ]; then
  set -a
  # shellcheck disable=SC1091
  source "/home/user/.env.trading"
  set +a
fi

export AI_RAG_QDRANT_URL="${AI_RAG_QDRANT_URL:-http://localhost:6333}"
export AI_RAG_EMBEDDING_PROVIDER="${AI_RAG_EMBEDDING_PROVIDER:-ollama}"
export AI_RAG_EMBEDDING_MODEL="${AI_RAG_EMBEDDING_MODEL:-nomic-embed-text}"

mkdir -p /home/user/logs

exec /usr/bin/flock -n "$LOCK_FILE" \
  "$PYTHON_BIN" "$SCRIPT" "$@"
