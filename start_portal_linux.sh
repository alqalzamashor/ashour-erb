#!/usr/bin/env bash
# تشغيل بوابة التجارب:  ./start_portal_linux.sh   |   رابط دعوة:  ./start_portal_linux.sh invite --count 10
cd "$(dirname "$0")"
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
if [ "$1" = "invite" ] || [ "$1" = "code" ] || [ "$1" = "remind" ] || [ "$1" = "list" ] || [ "$1" = "stop-all" ]; then exec "$PY" trial_portal.py "$@"; fi
exec "$PY" trial_portal.py run "$@"
