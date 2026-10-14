"""الباركود الموزون / المسعّر (EAN-13 متغير): بادئة + كود الصنف (PLU) + قيمة (وزن بالجرام أو سعر) + رقم تحقق.
مثال بالإعدادات الافتراضية: 20 00123 00850 C  (13 رقم) ->  الصنف اللي كوده/باركوده 00123 (أو 123)، الوزن 850 جم = 0.850 كجم.
الإعدادات في scale_barcode.json: prefix (بادئة أو أكتر، مفصولة بفاصلة)، plu_len، value_len، kind (weight|price)، weight_divisor (1000 = جرام→كجم)،
price_divisor (100 = قروش→ريال)، check_digit (التحقق من رقم EAN-13)."""
import json
import os

from . import audit
from .db import APP_DIR

CFG_PATH = os.path.join(APP_DIR, "scale_barcode.json")
DEFAULTS = {"enabled": True, "prefix": "20", "plu_len": 5, "value_len": 5, "kind": "weight", "weight_divisor": 1000, "price_divisor": 100, "check_digit": True}


def get_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


@audit.audited_config("إعدادات الباركود الموزون")
def save_config(**kw):
    from . import services
    services.require_action("settings", "edit")
    cfg = get_config()
    cfg.update({k: v for k, v in kw.items() if k in DEFAULTS})
    prefixes = [x.strip() for x in str(cfg["prefix"]).split(",") if x.strip()]
    if not prefixes or not all(x.isdigit() for x in prefixes):
        raise ValueError("البادئة أرقام فقط (مثل 2 أو 20,21)")
    cfg["plu_len"], cfg["value_len"] = int(cfg["plu_len"]), int(cfg["value_len"])
    if cfg["kind"] not in ("weight", "price"):
        raise ValueError("نوع القيمة: وزن أو سعر")
    cfg["weight_divisor"], cfg["price_divisor"] = float(cfg["weight_divisor"]), float(cfg["price_divisor"])
    if cfg["weight_divisor"] <= 0 or cfg["price_divisor"] <= 0:
        raise ValueError("المقسوم عليه لازم يكون أكبر من صفر")
    if min(len(prefixes[0]), 1) + cfg["plu_len"] + cfg["value_len"] + (1 if cfg["check_digit"] else 0) > 13 and any(len(p) + cfg["plu_len"] + cfg["value_len"] + (1 if cfg["check_digit"] else 0) > 13 for p in prefixes):
        raise ValueError("البادئة + كود الصنف + القيمة (+ رقم التحقق) أكبر من 13 رقم")
    cfg["prefix"] = ",".join(prefixes)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return cfg


def ean13_valid(code):
    if len(code) != 13 or not code.isdigit():
        return False
    s = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(code[:12]))
    return (10 - s % 10) % 10 == int(code[12])


def parse(code):
    """بيحلّل باركود موزون -> {plu, value, kind} أو None لو مش بصيغة الإعدادات (أو رقم التحقق غلط)."""
    cfg = get_config()
    code = (code or "").strip()
    if not cfg["enabled"] or not code.isdigit():
        return None
    for pre in str(cfg["prefix"]).split(","):
        pre = pre.strip()
        need = len(pre) + cfg["plu_len"] + cfg["value_len"] + (1 if cfg["check_digit"] else 0)
        if not pre or not code.startswith(pre) or len(code) != need:
            continue
        if cfg["check_digit"] and len(code) == 13 and not ean13_valid(code):
            continue
        i = len(pre)
        plu = code[i:i + cfg["plu_len"]]; raw = int(code[i + cfg["plu_len"]:i + cfg["plu_len"] + cfg["value_len"]])
        value = raw / (cfg["weight_divisor"] if cfg["kind"] == "weight" else cfg["price_divisor"])
        return {"plu": plu, "value": value, "kind": cfg["kind"], "prefix": pre}
    return None
