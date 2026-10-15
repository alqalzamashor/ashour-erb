"""تشغيل ashour كبرنامج ديسك توب: بيشغّل السيرفر على الجهاز نفسه (127.0.0.1) بقاعدة SQLite محلية ويفتح نافذة تطبيق مستقلة.
نفس الكود بتاع النسخة السحابية (server.py) - الفرق بس إن كل حاجة محلية على جهازك.

للربط بالسحابة (مزامنة مع المركز): حط ملف desktop.json في مجلد البيانات:
  {"node_id": "PC01", "hq_url": "https://your-server:8600", "sync_key": "المفتاح"}
أو اضبط ERP_NODE_ID / ERP_HQ_URL / ERP_SYNC_KEY. تفاصيل في README_DESKTOP_AR.md."""
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        if _s:
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:      # noqa: BLE001
        pass

PREFERRED_PORT = 8552


def data_home():
    """مجلد بيانات الديسك توب: ERP_HOME لو متحدد، وإلا مجلد المستخدم (ويندوز: %LOCALAPPDATA%\\ashour)."""
    env = os.environ.get("ERP_HOME", "").strip()
    if env:
        return os.path.abspath(env)
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "ashour")


def apply_cloud_config(home):
    """بيقرا desktop.json (لو موجود) ويحوّله لمتغيرات بيئة الفرع. بيرجّع True لو الربط مضبوط."""
    path = os.path.join(home, "desktop.json")
    if not os.path.exists(path):
        return False
    try:
        cfg = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        print("تحذير: desktop.json مش JSON سليم - اتجاهل.")
        return False
    for key, env in (("node_id", "ERP_NODE_ID"), ("hq_url", "ERP_HQ_URL"), ("sync_key", "ERP_SYNC_KEY")):
        if cfg.get(key):
            os.environ.setdefault(env, str(cfg[key]))
    return bool(cfg.get("node_id") and cfg.get("hq_url") and cfg.get("sync_key"))


def port_free(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


def pick_port():
    if port_free(PREFERRED_PORT):
        return PREFERRED_PORT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def is_ashour(port):
    """هل فيه نسخة ashour شغّالة بالفعل على البورت ده؟ (عشان نفتح لها نافذة بدل تشغيل نسخة تانية)"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
            return r.status == 200
    except Exception:      # noqa: BLE001
        return False


def wait_ready(port, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if not port_free(port):
            return True
        time.sleep(0.4)
    return False


def find_app_browser():
    """متصفح مبني على Chromium (Chrome / Edge / Brave / Chromium) لفتح نافذة تطبيق من غير شريط عناوين."""
    names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "microsoft-edge-stable", "brave-browser"]
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    rel = [r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe", r"BraveSoftware\Brave-Browser\Application\brave.exe"]
    for root in filter(None, roots):
        for r in rel:
            p = os.path.join(root, r)
            if os.path.exists(p):
                return p
    mac = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    return next((p for p in mac if os.path.exists(p)), None)


def open_window(url, home):
    """بيفتح نافذة التطبيق. بيرجّع كائن العملية لو نافذة مستقلة (قفلها = إيقاف البرنامج)، أو None لو اتفتح في المتصفح العادي."""
    exe = find_app_browser()
    if exe:
        profile = os.path.join(home, "window-profile")      # بروفايل مستقل عشان العملية تفضل عايشة لحد قفل النافذة
        os.makedirs(profile, exist_ok=True)
        try:
            return subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", "--lang=ar", "--window-size=1366,820"])
        except OSError:
            pass
    import webbrowser
    webbrowser.open(url)
    return None


def show_first_password(home):
    path = os.path.join(home, "initial_admin_password.txt")
    if not os.path.exists(path):
        return
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk(); root.withdraw()
        messagebox.showinfo("ashour", "أول تشغيل. بيانات دخول المدير (admin):\n\n" + open(path, encoding="utf-8").read().strip() + "\n\nاحفظها وغيّرها من شاشة المستخدمين.")
        root.destroy()
    except Exception:      # noqa: BLE001
        print("كلمة مرور المدير الأولى في:", path)


def main(argv=None):
    home = data_home()
    os.makedirs(home, exist_ok=True)
    os.environ["ERP_HOME"] = home                          # لازم قبل استيراد erp_app.db
    os.environ.setdefault("ERP_INTERNAL_HOST", "127.0.0.1")
    synced = apply_cloud_config(home)
    if port_free(PREFERRED_PORT) is False and is_ashour(PREFERRED_PORT):
        print("ashour شغّال بالفعل - بفتح نافذة له.")
        open_window(f"http://127.0.0.1:{PREFERRED_PORT}", home)
        return 0
    port = pick_port()
    url = f"http://127.0.0.1:{port}"
    print(f"ashour ديسك توب - البيانات في {home}" + (" - مربوط بالسحابة" if synced else " - محلي (من غير ربط سحابي)"))

    def launcher():
        if not wait_ready(port):
            print("السيرفر لم يبدأ في الوقت المناسب")
            return
        show_first_password(home)
        proc = open_window(url, home)
        if proc is not None:
            proc.wait()              # قفل النافذة = إيقاف البرنامج
            os._exit(0)

    threading.Thread(target=launcher, daemon=True).start()
    import server
    return server.run(["--host", "127.0.0.1", "--port", str(port)])


if __name__ == "__main__":
    raise SystemExit(main())
