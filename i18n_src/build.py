"""بيجمّع ملفات i18n_src/*.txt (سطر = عربي=English) في erp_app/data/i18n_en.json.  التشغيل: python i18n_src/build.py"""
import glob, json, os
here = os.path.dirname(os.path.abspath(__file__))
d = {}
for f in sorted(glob.glob(os.path.join(here, "p*.txt"))):
    for ln in open(f, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if "=" not in ln:
            continue
        a, _, b = ln.partition("=")
        if a.strip() and b.strip():
            d[a.strip()] = b.strip()
pf = os.path.join(here, "patterns.json")
if os.path.exists(pf):
    d["__patterns__"] = json.load(open(pf, encoding="utf-8"))
out = os.path.join(here, "..", "erp_app", "data", "i18n_en.json")
json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(d), "entries ->", os.path.normpath(out))
