#!/bin/bash
cd /home/scottk/Projects/onui-ai
source .venv/bin/activate

# Load .env explicitly so all vars (including those PM2 may miss) are set
set -a
source .env
set +a

export ONUI_TMP_DIR="${ONUI_TMP_DIR:-/home/scottk/Projects/onui-ai/data/tmp}"
export TMPDIR="${TMPDIR:-$ONUI_TMP_DIR}"
export TEMP="${TEMP:-$ONUI_TMP_DIR}"
export TMP="${TMP:-$ONUI_TMP_DIR}"
mkdir -p "$ONUI_TMP_DIR"

exec .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 9002 --loop uvloop --http httptools
