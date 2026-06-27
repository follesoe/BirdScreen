#!/usr/bin/env bash
#
# BirdScreen dev mode — edit and just refresh (frontend hot-reloads on its own;
# the backend auto-restarts on Python changes, so a browser refresh picks those up).
#
# Runs two processes:
#   1. FastAPI (uvicorn --reload)  on http://127.0.0.1:8000   (the API)
#   2. Vite dev server (HMR)       on http://<this-host>:5173 (open THIS one)
#
# Vite proxies /api → :8000, so open the Vite URL it prints. Ctrl-C stops both.
# Note: stop any other server using port 8000 first.
#
set -euo pipefail
cd "$(dirname "$0")/.."

# Backend with auto-reload, watching only the Python source.
uv run --extra web uvicorn birdscreen.web.app:create_app \
  --factory --reload --reload-dir src --host 127.0.0.1 --port 8000 &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM

# Vite dev server with hot-module reload; --host also exposes it on the LAN.
npm --prefix frontend run dev -- --host
