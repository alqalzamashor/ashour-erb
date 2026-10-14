"""بيولّد أيقونة التطبيق (1024) وخلفيتها وشاشة البداية من اللوجو في erp_app/brand.py -> مجلد resources (يستعملها @capacitor/assets)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from erp_app import brand
out = sys.argv[1] if len(sys.argv) > 1 else "resources"
os.makedirs(out, exist_ok=True)
brand.mark(1024, True).save(os.path.join(out, "icon-only.png"))
brand.mark(1024, True).save(os.path.join(out, "icon.png"))
fg = brand.mark(1024, False)                      # للأندرويد adaptive: العلامة على شفاف
from PIL import Image
fgc = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)); small = brand.mark(640, False); fgc.paste(small, (192, 192), small); fgc.save(os.path.join(out, "icon-foreground.png"))
Image.new("RGBA", (1024, 1024), "#124F40").save(os.path.join(out, "icon-background.png"))
sp = Image.new("RGBA", (2732, 2732), "#124F40"); m = brand.mark(720, False); sp.paste(m, ((2732 - 720) // 2,) * 2, m)
sp.save(os.path.join(out, "splash.png")); sp.save(os.path.join(out, "splash-dark.png"))
print("تم ->", out)
