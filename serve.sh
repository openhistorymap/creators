#!/usr/bin/env bash
# Static preview server. The page fetches the CSVs, so file:// will not work.
set -e
cd "$(dirname "$0")"
PORT="${1:-8088}"
echo "→ http://localhost:${PORT}/"
exec python3 -m http.server "$PORT"
