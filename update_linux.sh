#!/usr/bin/env bash
# ترقية آمنة:  ./update_linux.sh الإصدار.zip [--check]
cd "$(dirname "$0")"
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python || { [ -x venv/bin/python ] && PY=venv/bin/python; }
exec "$PY" update.py "$@"
