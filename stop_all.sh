#!/bin/bash
# MoonshotX — Stop all backend and frontend processes
set -e

BACKEND_PID_FILE="/tmp/moonshotx_backend.pid"
FRONTEND_PID_FILE="/tmp/moonshotx_frontend.pid"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${CYAN}[MoonshotX]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║      MoonshotX — Stop All Services   ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

log "Stopping all processes..."

# ── 1. Kill by PID files ──────────────────────────────────────────────────────
for pidfile in "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"; do
    if [ -f "$pidfile" ]; then
        pid=$(cat "$pidfile" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && ok "Killed PID $pid ($pidfile)"
        fi
        rm -f "$pidfile"
    fi
done

# ── 2. Kill by port (belt + suspenders) ──────────────────────────────────────
for port in 8001 3000; do
    pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        ok "Killed process(es) on port $port"
    fi
done

# ── 3. Kill any stray uvicorn / yarn / node for this project ─────────────────
pkill -f "uvicorn server:app" 2>/dev/null && ok "Killed stray uvicorn processes" || true
pkill -f "moonshotx.*yarn"    2>/dev/null && ok "Killed stray yarn processes" || true

sleep 1

echo ""
ok "All MoonshotX processes stopped"
echo ""
