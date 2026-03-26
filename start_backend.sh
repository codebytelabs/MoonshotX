#!/bin/bash
# MoonshotX — Start Backend
set -e

BACKEND_DIR="$(dirname "$0")/backend"
VENV="$BACKEND_DIR/venv"

echo "🚀 Starting MoonshotX Backend..."
echo "   MongoDB: $(mongosh --eval 'db.runCommand({connectionStatus:1}).ok' --quiet 2>/dev/null && echo 'connected' || echo 'check mongod')"

cd "$BACKEND_DIR"
"$VENV/bin/uvicorn" server:app --host 0.0.0.0 --port 8001 --reload
