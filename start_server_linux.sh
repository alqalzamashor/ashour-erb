#!/usr/bin/env bash
# تشغيل السيرفر:  ./start_server_linux.sh  [--port 8552]
cd "$(dirname "$0")"
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" server.py "$@"
