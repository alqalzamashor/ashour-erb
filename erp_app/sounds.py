"""أصوات الجرد/المطبخ (نجاح / مكرر / خطأ / إنهاء) - بتتولّد برمجيًا كملفات WAV وبتتخدم كملفات ثابتة من السيرفر،
والتشغيل بيحصل في متصفح المستخدم نفسه (flet-audio). لو الصوت مش متاح الشاشة بتعتمد على التنبيه المرئي."""
import io
import math
import os
import struct
import wave

RATE = 22050


def _tone(freq, ms, vol=0.55, shape="sine", fade_ms=10):
    n = int(RATE * ms / 1000.0)
    fade = max(1, int(RATE * fade_ms / 1000.0))
    out = []
    for i in range(n):
        ph = 2 * math.pi * freq * i / RATE
        v = math.sin(ph) if shape == "sine" else (1.0 if math.sin(ph) >= 0 else -1.0) * 0.6
        env = min(1.0, i / fade, (n - 1 - i) / fade)
        out.append(int(32767 * vol * v * env))
    return out


def _silence(ms):
    return [0] * int(RATE * ms / 1000.0)


SOUND_DEFS = {
    "ok": lambda: _tone(1000, 70) + _tone(1500, 95),                                  # صوتين طالعين = تمام
    "dup": lambda: _tone(700, 95) + _silence(70) + _tone(700, 95),                    # بيبين متطابقين = مكرر
    "error": lambda: _tone(180, 420, vol=0.6, shape="square", fade_ms=25),            # طنين واطي = غلط/مش موجود
    "done": lambda: _tone(523, 110) + _tone(659, 110) + _tone(784, 180),              # دو-مي-صول = خلصنا
}


def wav_bytes(kind):
    if kind not in SOUND_DEFS:
        raise ValueError(f"صوت غير معروف: {kind}")
    samples = SOUND_DEFS[kind]()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return buf.getvalue()


SOUNDS_SUBDIR = "sounds"


def publish_sounds(assets_dir):
    """يكتب ملفات الصوت في مجلد الملفات الثابتة (مرة عند بدء السيرفر)."""
    d = os.path.join(assets_dir, SOUNDS_SUBDIR)
    os.makedirs(d, exist_ok=True)
    for k in SOUND_DEFS:
        p = os.path.join(d, f"{k}.wav")
        if not os.path.exists(p):
            with open(p, "wb") as f:
                f.write(wav_bytes(k))


def play(kind, enabled=True, page=None):
    """يشغّل الصوت في متصفح المستخدم الحالي من غير ما يوقف الشاشة. بيرجّع True لو اتبعت للتشغيل."""
    if not enabled or kind not in SOUND_DEFS:
        return False
    try:
        import flet as ft
        import flet_audio as fa
        page = page or ft.context.page
        au = getattr(page, "_erp_audio", None)
        if au is None:
            au = fa.Audio(src=f"{SOUNDS_SUBDIR}/{kind}.wav", autoplay=False)
            page.services.append(au)
            page._erp_audio = au
            page.update()
        au.src = f"{SOUNDS_SUBDIR}/{kind}.wav"
        au.update()

        async def _go():
            try:
                await au.play()
            except Exception:
                pass
        page.run_task(_go)
        return True
    except Exception:
        return False
