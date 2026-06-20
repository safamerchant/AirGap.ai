#!/usr/bin/env bash
# Starts the Airgap backend (:5000) and serves the redesign frontend (:8000).
set -e
cd "$(dirname "$0")"

echo "Installing backend deps..."
pip install -r backend/requirements.txt -q

echo "Starting backend on http://localhost:5000 ..."
( cd backend && python app.py ) &
BACK=$!

echo "Serving frontend on http://localhost:8000 ..."
( cd frontend && python -m http.server 8000 ) &
FRONT=$!

trap "kill $BACK $FRONT 2>/dev/null" EXIT
echo ""
echo "  ▶ Open:  http://localhost:8000/airgap-console.html"
echo "  (Ctrl-C to stop both)"
echo ""
wait
