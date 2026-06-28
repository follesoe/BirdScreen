#!/usr/bin/env bash
#
# BirdScreen dev mode — edit and just refresh (frontend hot-reloads on its own;
# the backend auto-restarts on Python changes, so a browser refresh picks those up).
#
# Runs two processes:
#   1. FastAPI (uvicorn --reload)  on http://<this-host>:8000  (API + built dist)
#   2. Vite dev server (HMR)       on http://<this-host>:5173  (open THIS one)
#
# For live editing open the Vite URL (:5173) — e.g. http://jonas-macbook.local:5173 —
# it hot-reloads and proxies /api → :8000. The :8000 URL serves the last `npm run
# build` (rebuild to refresh it). Both bind 0.0.0.0 so they work over the LAN.
# Ctrl-C stops both. Note: stop any other server using port 8000 first.
#
set -euo pipefail
cd "$(dirname "$0")/.."

# Backend with auto-reload, watching only the Python source.
uv run --extra web uvicorn birdscreen.web.app:create_app \
  --factory --reload --reload-dir src --host 0.0.0.0 --port 8000 &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM

# Vite dev server with hot-module reload; --host also exposes it on the LAN.
npm --prefix frontend run dev -- --host
