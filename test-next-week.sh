#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.11+ was not found. Set PYTHON_BIN to your Python executable." >&2
  exit 1
fi
exec "$PYTHON_BIN" tools/test_drive.py
