#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"

SNAPSHOT="../axm-monolith-test/snapshot"
if [ -f "$SNAPSHOT/START_AXM.sh" ]; then
  echo "Existing AXM monolith snapshot found."
  echo "Launching the complete captured stack..."
  exec "$SNAPSHOT/START_AXM.sh"
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.11+ was not found. Set PYTHON_BIN to your Python executable." >&2
  exit 1
fi

echo "No completed monolith snapshot exists yet."
echo "Opening the guided first-build flow..."
exec "$PYTHON_BIN" tools/test_week_plus.py
