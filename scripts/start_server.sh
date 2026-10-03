#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)

BASE_DIR="${RADIO_WORKSPACE:-$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)}"
if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x "$BASE_DIR/.venv-analysis/bin/python3" ]; then
    PYTHON_BIN="$BASE_DIR/.venv-analysis/bin/python3"
  elif [ -x /Library/Developer/CommandLineTools/usr/bin/python3 ]; then
    PYTHON_BIN=/Library/Developer/CommandLineTools/usr/bin/python3
  else
    PYTHON_BIN=python3
  fi
fi
if ! "$PYTHON_BIN" "$SCRIPT_DIR/generate_feed.py"; then
  printf '%s\n' "Warning: feed refresh failed; serving saved files." >&2
fi
if ! "$PYTHON_BIN" "$SCRIPT_DIR/generate_study_site.py"; then
  printf '%s\n' "Warning: study library refresh failed; serving saved files." >&2
fi
exec "$PYTHON_BIN" "$SCRIPT_DIR/podcast_server.py"
