"""اختبار المزامنة بنسختين حقيقيتين (عمليتين): مركز بيشغّل API داخلي، وفرع بيشتغل محليًا ثم يزامن."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HQ_CODE = r'''
import os, sys, time
sys.path.insert(0, %(root)r)
from erp_app import db, services, nodesync
db.init_db()
services.set_current_user(services.authenticate_user("admin", "admin"))
services.update_company_settings(name="مركز", vat_number="300123456700003")
cust = services.create_customer(name="عميل")
services.create_product("G1", "سلعة", sale_price=30, cost_price=12, product_type="service")
key = nodesync.add_node("BR01", "فرع 1")
open(%(keyfile)r, "w").write(key)
from erp_app import delivery_server
print(delivery_server.start("127.0.0.1", %(port)d), flush=True)
open(%(ready)r, "w").write("1")
time.sleep(120)
'''
NODE_CODE = r'''
import os, sys, json
sys.path.insert(0, %(root)r)
from erp_app import db, services, nodesync
db.init_db()
services.set_current_user(services.authenticate_user("admin", "admin"))
nodesync.install()
mode = sys.argv[1]
if mode == "first":
    r = nodesync.cycle()           # أول سحب لنسخة المركز
    print(json.dumps(r, ensure_ascii=False))
elif mode == "work":
    cid = services.list_customers()[0].id
    pid = services.list_products()[0].id
    inv = services.create_sales_invoice(cid, [{"product_id": pid, "quantity": 2, "unit_price": 30}])
    services.create_receipt(cid, 10, 1) if False else None
    print(json.dumps({"inv": inv, "counts": nodesync.counts()}))
elif mode == "sync":
    r = nodesync.cycle(); r2 = nodesync.cycle()
    print(json.dumps({"r": r, "r2": r2, "counts": nodesync.counts()}, ensure_ascii=False, default=str))
elif mode == "offline":
    r = nodesync.cycle()
    print(json.dumps({"r": r, "counts": nodesync.counts()}, ensure_ascii=False))
'''


def _port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _run(code, home, args, env_extra):
    env = {**os.environ, "ERP_HOME": home, "PYTHONUTF8": "1", **env_extra}
    env.pop("ERP_DATABASE_URL", None)
    f = os.path.join(home, "_run.py")
    open(f, "w", encoding="utf-8").write(code)
    return subprocess.run([sys.executable, f, *args], env=env, capture_output=True, text=True, timeout=180, cwd=ROOT)


def test_branch_sync_end_to_end():
    hq_home, br_home = tempfile.mkdtemp(prefix="hq_"), tempfile.mkdtemp(prefix="br_")
    port = _port()
    keyfile, ready = os.path.join(hq_home, "key.txt"), os.path.join(hq_home, "ready")
    code = HQ_CODE % {"root": ROOT, "keyfile": keyfile, "port": port, "ready": ready}
    open(os.path.join(hq_home, "_hq.py"), "w", encoding="utf-8").write(code)
    env = {**os.environ, "ERP_HOME": hq_home, "PYTHONUTF8": "1"}
    env.pop("ERP_DATABASE_URL", None)
    hq = subprocess.Popen([sys.executable, os.path.join(hq_home, "_hq.py")], env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        for _ in range(100):
            if os.path.exists(ready):
                break
            time.sleep(0.2)
        assert os.path.exists(ready), hq.stderr.read() if hq.poll() is not None else "hq not ready"
        key = open(keyfile).read().strip()
        node_env = {"ERP_NODE_ID": "BR01", "ERP_SYNC_KEY": key, "ERP_HQ_URL": "http://127.0.0.1:%d" % port}
        nc = NODE_CODE % {"root": ROOT}
        r = _run(nc, br_home, ["first"], node_env)
        assert r.returncode == 0, r.stderr[-1500:]
        assert json.loads(r.stdout.strip().splitlines()[-1])["ok"] is True
        r = _run(nc, br_home, ["work"], node_env)
        assert r.returncode == 0, r.stderr[-1500:]
        w = json.loads(r.stdout.strip().splitlines()[-1])
        assert w["counts"]["pending"] == 1
        # مركز مقفول (بورت غلط) => offline والعملية تفضل معلّقة
        r = _run(nc, br_home, ["offline"], {**node_env, "ERP_HQ_URL": "http://127.0.0.1:%d" % _port()})
        o = json.loads(r.stdout.strip().splitlines()[-1])
        assert o["r"]["offline"] is True and o["counts"]["pending"] == 1
        # اتصال سليم
        r = _run(nc, br_home, ["sync"], node_env)
        assert r.returncode == 0, r.stderr[-1500:]
        d = json.loads(r.stdout.strip().splitlines()[-1])
        assert d["r"]["ok"] and d["counts"] == {"pending": 0, "failed": 0, "pushed": 1}
        # التكرار: دورة تانية ما تعيدش التنفيذ
        assert d["r2"]["push"]["sent"] == 0
        # عند المركز: الفاتورة اتسجّلت مرة واحدة
        q = r"""
import sys; sys.path.insert(0, %r)
from erp_app import db
with db.get_session() as s:
    print(s.query(db.SalesInvoice).count(), s.query(db.SyncInbox).count())
""" % ROOT
        qr = _run(q, hq_home, [], {})
        assert qr.stdout.strip().split() == ["1", "1"], qr.stdout + qr.stderr[-800:]
    finally:
        hq.kill()


def test_codec_roundtrip():
    from erp_app import nodesync as n
    import datetime
    v = {"a": [1, 2.5, datetime.datetime(2026, 1, 2, 3, 4, 5), datetime.date(2026, 1, 2), b"xy"], "b": {"c": None}}
    assert n.dec(json.loads(json.dumps(n.enc(v)))) == v


def test_not_node_is_noop():
    from erp_app import nodesync as n
    assert n.is_node() is False and n.install() == 0
