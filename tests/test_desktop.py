"""الديسك توب: مجلد البيانات، ربط السحابة من desktop.json، اختيار البورت، وتشغيل حقيقي لحد ما الصفحة ترد."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import desktop

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_data_home_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ERP_HOME", str(tmp_path))
    assert desktop.data_home() == str(tmp_path)
    monkeypatch.delenv("ERP_HOME")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert desktop.data_home() == os.path.join(str(tmp_path), "ashour")


def test_cloud_config(monkeypatch, tmp_path):
    for k in ("ERP_NODE_ID", "ERP_HQ_URL", "ERP_SYNC_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert desktop.apply_cloud_config(str(tmp_path)) is False
    (tmp_path / "desktop.json").write_text(json.dumps({"node_id": "PC01", "hq_url": "https://hq:8600", "sync_key": "k"}), encoding="utf-8")
    assert desktop.apply_cloud_config(str(tmp_path)) is True
    assert os.environ["ERP_NODE_ID"] == "PC01" and os.environ["ERP_HQ_URL"] == "https://hq:8600"
    for k in ("ERP_NODE_ID", "ERP_HQ_URL", "ERP_SYNC_KEY"):
        os.environ.pop(k, None)
    (tmp_path / "desktop.json").write_text("{bad", encoding="utf-8")
    assert desktop.apply_cloud_config(str(tmp_path)) is False


def test_pick_port_when_busy(monkeypatch):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1); p = s.getsockname()[1]
    monkeypatch.setattr(desktop, "PREFERRED_PORT", p)
    try:
        q = desktop.pick_port()
        assert q != p and desktop.port_free(q)
    finally:
        s.close()
    assert desktop.pick_port() == p


def test_desktop_boots_locally(tmp_path):
    """بيشغّل desktop.py فعليًا (من غير نافذة) ويتأكد إن الصفحة بترد على 127.0.0.1 بس."""
    env = dict(os.environ, ERP_HOME=str(tmp_path), PATH="/nonexistent", DISPLAY="")
    env["PATH"] = os.path.dirname(sys.executable)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    code = f"import desktop, webbrowser; webbrowser.open=lambda u,*a,**k: None; desktop.PREFERRED_PORT={port}; desktop.find_app_browser=lambda: None; raise SystemExit(desktop.main())"
    p = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ok = False
        for _ in range(120):
            time.sleep(0.5)
            try:
                ok = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).status == 200
                break
            except Exception:      # noqa: BLE001
                continue
        assert ok, "الديسك توب مردّش"
        assert os.path.exists(os.path.join(str(tmp_path), "data", "erp.db"))
        assert os.path.exists(os.path.join(str(tmp_path), "initial_admin_password.txt"))
    finally:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
