#!/bin/bash
# MoonshotX — Start Frontend
set -e

FRONTEND_DIR="$(dirname "$0")/frontend"
echo "🌐 Starting MoonshotX Frontend on http://localhost:3000"
cd "$FRONTEND_DIR"
yarn start
