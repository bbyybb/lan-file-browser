#!/bin/bash
# ============================================
#   LAN File Browser - Stop Server (macOS / Linux)
# ============================================

# Default port, change if you used --port to start
PORT=${1:-25600}

echo "============================================"
echo "  LAN File Browser - Stop Server"
echo "============================================"
echo ""

# [1/3] Find process on the port (try multiple tools for compatibility)
echo "[1/3] Searching for process on port $PORT..."
PID=""

if command -v lsof >/dev/null 2>&1; then
    PID=$(lsof -ti :$PORT 2>/dev/null)
elif command -v ss >/dev/null 2>&1; then
    PID=$(ss -tlnp "sport = :$PORT" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u)
elif command -v fuser >/dev/null 2>&1; then
    PID=$(fuser $PORT/tcp 2>/dev/null)
else
    echo "[ERROR] No supported tool found (lsof, ss, or fuser)."
    echo "Please install one of them or manually kill the process."
    exit 1
fi

if [ -z "$PID" ]; then
    echo ""
    echo "[OK] No process found on port $PORT. Server is not running."
    exit 0
fi

echo "Found process PID: $PID"
echo ""

# [2/3] Show process details
echo "[2/3] Process details:"
for p in $PID; do
    ps -p "$p" -o pid,user,command 2>/dev/null
done
echo ""

# [3/3] Stop the process (graceful first, then force)
echo "[3/3] Stopping process..."
kill $PID 2>/dev/null

# Wait 2 seconds, then force kill if still running
sleep 2
for p in $PID; do
    if kill -0 "$p" 2>/dev/null; then
        echo "Process $p still running, force killing..."
        kill -9 "$p" 2>/dev/null
    fi
done

echo ""
echo "[OK] Server stopped successfully! (PID: $PID)"
