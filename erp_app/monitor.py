"""إشارات نشاط خفيفة للمراقبة: آخر دخول لكل نسخة (ملف activity.json في مجلد البيانات، بتقراه بوابة التجارب)."""
import datetime
import json
import os

from .db import APP_DIR

PATH = os.path.join(APP_DIR, "activity.json")


def mark_login(username):
    try:
        data = {"last_login": datetime.datetime.now().isoformat(timespec="seconds"), "user": str(username)[:80]}
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, PATH)
    except Exception:      # noqa: BLE001 - المراقبة ما تكسرش الدخول
        pass
