#!/usr/bin/env sh
# Cross-platform helper: Linux / macOS
# Starts ATNF Pulsar Query Center and opens the browser.
set -e
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$DIR"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "error: python3/python not found in PATH" >&2
  exit 1
fi

exec "$PY" "$DIR/start.py" "$@"
