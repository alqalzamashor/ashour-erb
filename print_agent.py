#!/usr/bin/env python3
"""وكيل الطباعة - بيتثبّت على جهاز الكاشير/المطبخ (اللي الطابعة الحرارية متوصّلة بيه) لما البرنامج شغّال على سيرفر بعيد.
بيسحب أوامر الطباعة من السيرفر كل ثانيتين ويبعتها للطابعة المحلية، ويبلّغ السيرفر بالنتيجة. ملف واحد، من غير أي مكتبات خارجية.

مثال (طابعة شبكة):   python print_agent.py --url https://erp.example.com --token XXXX --station receipt --mode network --address 192.168.1.50
مثال (طابعة مثبتة):  python print_agent.py --url https://erp.example.com --token XXXX --station receipt --mode system --address "POS-80"
مثال (منفذ):         python print_agent.py ... --mode file --address /dev/usb/lp0      (أو COM3 على ويندوز)

--url: عنوان وكيل الطباعة على السيرفر (البورت الداخلي 8600 أو عنوان الـ proxy اللي بيمرّر /agent/). المتغيرات: ERP_AGENT_URL / ERP_AGENT_TOKEN.
المفتاح بتلاقيه في شاشة «الطابعات الحرارية» بعد ما تختار طريقة «وكيل طباعة»."""
import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def send(mode, addr, port, data):
    if mode == "network":
        with socket.create_connection((addr, int(port)), timeout=5) as s:
            s.sendall(data)
    elif mode == "file":
        with open(addr, "ab" if addr.startswith(("/dev/", "COM", "\\\\")) else "wb") as f:
            f.write(data)
    elif mode == "system":
        if sys.platform.startswith("win"):
            try:
                import win32print
                h = win32print.OpenPrinter(addr)
                try:
                    win32print.StartDocPrinter(h, 1, ("ERP", None, "RAW")); win32print.StartPagePrinter(h)
                    win32print.WritePrinter(h, data); win32print.EndPagePrinter(h); win32print.EndDocPrinter(h)
                finally:
                    win32print.ClosePrinter(h)
            except ImportError:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tf:
                    tf.write(data)
                try:
                    r = subprocess.run(["cmd", "/c", "copy", "/b", tf.name, f"\\\\localhost\\{addr}"], capture_output=True, text=True, timeout=15)
                    if r.returncode != 0:
                        raise RuntimeError("ثبّت pywin32 أو شارك الطابعة باسمها: " + (r.stdout or r.stderr)[:120])
                finally:
                    os.remove(tf.name)
        else:
            r = subprocess.run(["lp", "-d", addr, "-o", "raw"], input=data, capture_output=True, timeout=15)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.decode(errors="ignore")[:120])
    else:
        raise RuntimeError("طريقة غير معروفة: " + mode)


def call(url, token, method="GET", body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def run_once(a):
    """دورة واحدة: بتسحب الأوامر وتطبعها وتبلّغ. بترجّع عدد الأوامر."""
    base = a.url.rstrip("/")
    res = call(f"{base}/agent/jobs?station={a.station}", a.token)
    n = 0
    for j in res.get("jobs", []):
        try:
            send(a.mode, a.address, a.port, base64.b64decode(j["data"]))
            out = {"ok": True}
        except Exception as ex:      # noqa: BLE001
            out = {"ok": False, "error": str(ex)[:250]}
            print("فشل الطباعة:", ex, file=sys.stderr)
        try:
            call(f"{base}/agent/jobs/{j['id']}", a.token, "POST", out)
        except Exception as ex:      # noqa: BLE001
            print("تعذر إبلاغ السيرفر:", ex, file=sys.stderr)
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description="وكيل الطباعة الحرارية")
    ap.add_argument("--url", default=os.environ.get("ERP_AGENT_URL"), required=not os.environ.get("ERP_AGENT_URL"))
    ap.add_argument("--token", default=os.environ.get("ERP_AGENT_TOKEN"), required=not os.environ.get("ERP_AGENT_TOKEN"))
    ap.add_argument("--station", choices=["receipt", "kitchen"], default="receipt")
    ap.add_argument("--mode", choices=["network", "system", "file"], required=True)
    ap.add_argument("--address", required=True)
    ap.add_argument("--port", type=int, default=9100)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    print(f"وكيل الطباعة شغّال ({a.station}) → {a.url}")
    while True:
        try:
            run_once(a)
        except urllib.error.HTTPError as ex:
            print("رفض السيرفر:", ex.code, "- راجع المفتاح" if ex.code == 401 else "", file=sys.stderr)
        except Exception as ex:      # noqa: BLE001
            print("تعذر الاتصال بالسيرفر:", ex, file=sys.stderr)
        if a.once:
            break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
