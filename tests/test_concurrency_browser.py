"""إثبات أن مستخدمًا بينفّذ عملية تقيلة ما بيوقفش مستخدمًا تانيًا (متصفح حقيقي). بيتخطّى لو Playwright/Chromium مش موجودين."""
import json
import os
import socket
import subprocess
import sys
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP = '''
import os, sys, time, json
sys.path.insert(0, %r)
os.environ["FLET_FORCE_WEB_SERVER"] = "true"
import flet as ft
from erp_app import concurrency
concurrency.install(force=os.environ["MODE"] == "threads")
LOG = os.environ["LOGF"]
def log(n):
    open(LOG, "a").write(json.dumps([time.time(), n]) + "\\n")
def main(page: ft.Page):
    page.padding = 0
    def heavy(e):
        log("heavy"); time.sleep(3)
    def light(e):
        log("light")
    page.add(ft.Column([ft.FilledButton("h", width=300, height=80, on_click=heavy), ft.FilledButton("l", width=300, height=80, on_click=light)], spacing=0))
ft.run(main, view=ft.AppView.WEB_BROWSER, host="127.0.0.1", port=int(os.environ["PORT"]), no_cdn=True)
''' % ROOT


def _free():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _run(mode, tmp_path):
    app = tmp_path / f"app_{mode}.py"
    app.write_text(APP)
    logf = tmp_path / f"{mode}.log"
    port = _free()
    proc = subprocess.Popen([sys.executable, str(app)], env={**os.environ, "MODE": mode, "LOGF": str(logf), "PORT": str(port)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
                break
            except OSError:
                time.sleep(0.5)
        with pw.sync_playwright() as p:
            try:
                b = p.chromium.launch(args=["--no-sandbox"])
            except Exception:
                pytest.skip("Chromium غير متاح")
            pa = b.new_context(viewport={"width": 400, "height": 400}, locale="ar-EG").new_page()
            pb = b.new_context(viewport={"width": 400, "height": 400}, locale="ar-EG").new_page()
            for pg in (pa, pb):
                pg.goto(f"http://127.0.0.1:{port}")
            pa.wait_for_timeout(7000)
            pa.mouse.click(150, 40)
            time.sleep(0.5)
            t_light = time.time()
            pb.mouse.click(150, 120)
            time.sleep(5)
            b.close()
        ev = {n: t for t, n in (json.loads(l) for l in logf.read_text().splitlines())}
        return ev["light"] - t_light
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_heavy_handler_does_not_block_other_users(tmp_path):
    loop_delay = _run("loop", tmp_path)
    thread_delay = _run("threads", tmp_path)
    assert loop_delay > 1.5, f"المتوقع إن الوضع القديم يتأخر ({loop_delay:.2f}s)"
    assert thread_delay < 1.0, f"مع الخيوط المفروض يرد فورًا ({thread_delay:.2f}s)"
