#!/bin/sh
cd "$(dirname "$0")" && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && echo "تم. شغّل السيرفر:  . .venv/bin/activate && python server.py   (أو ./start_server_linux.sh)"
