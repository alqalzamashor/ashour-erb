"""شاشات «تقارير عاشور»: أرباح وخسائر الفروع، مبيعات نقاط البيع، المشتريات، العملاء والموردين، وإعداداتها."""
import datetime
import flet as ft
from .. import ashour_reports as ar, services, theme

LRM = "‎"
NOTE_COLORS = {"urgent": ("#FDECEA", "#B3261E"), "good": ("#E6F4EA", "#1E7B34"), "watch": ("#FFF4E0", "#9A6700"), "info": ("#E8F0FE", "#1A56B0")}


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        s = f"{v:,.2f}"
        return (LRM + s) if v < 0 else s
    return str(v)


def render_table(rep):
    """تقرير (dict) -> عناصر واجهة: ملاحظات + جدول."""
    parts = []
    for n in rep.get("notes") or []:
        bg, fg = NOTE_COLORS.get(n["level"], NOTE_COLORS["info"])
        body = [ft.Text(n["title"], weight=ft.FontWeight.BOLD, color=fg, size=13)]
        if n.get("text"):
            body.append(ft.Text(n["text"], size=12, color=fg))
        body += [ft.Text("• " + it, size=12, color=fg) for it in n.get("items") or []]
        parts.append(ft.Container(bgcolor=bg, border_radius=10, padding=ft.Padding(left=14, right=14, top=8, bottom=8), content=ft.Column(body, spacing=2)))
    cols = [ft.DataColumn(ft.Text(c, weight=ft.FontWeight.BOLD, size=12.5), numeric=i > 0) for i, c in enumerate(rep["columns"])]
    rows = []
    for r in rep["rows"]:
        kind = r["kind"]
        bold = kind in ("section", "total", "grand")
        color = {"section": theme.PRIMARY_LIGHT, "total": theme.SURFACE_ALT if hasattr(theme, "SURFACE_ALT") else None, "grand": theme.WARNING_LIGHT}.get(kind)
        cells = []
        for j, v in enumerate(r["cells"]):
            txt = _fmt(v)
            clr = None
            if isinstance(v, str) and v.startswith(("+", "-")) and v.endswith("%") and len(v) > 2:
                clr = theme.SUCCESS if v.startswith("+") else theme.DANGER
            elif isinstance(v, float) and v < 0:
                clr = theme.DANGER
            cells.append(ft.DataCell(ft.Text(txt, size=12.5, weight=ft.FontWeight.BOLD if bold else None, color=clr,
                                             selectable=True)))
        rows.append(ft.DataRow(cells=cells, color=color))
    if rows:
        parts.append(theme.h_scroll(ft.DataTable(columns=cols, rows=rows, heading_row_height=44, data_row_min_height=36, column_spacing=22)))
    else:
        parts.append(ft.Text("مفيش بيانات في الفترة دي", color=theme.TEXT_MUTED))
    return ft.Column(parts, spacing=10)


def _screen(page, title, subtitle, icon, kinds, runner, controls_fn=None, compare=True, single_range=True):
    """kinds: [(key, label)]. runner(kind, d_from, d_to, c_from, c_to, extras) -> report dict."""
    today = datetime.date.today()
    first = today.replace(day=1)
    last_end = first - datetime.timedelta(days=1)
    last_start = last_end.replace(day=1)
    prev_end = last_start - datetime.timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    fmt = "%Y-%m-%d"
    rng = theme.DateRangeField("الفترة", page, width=280, start=last_start.strftime(fmt), end=last_end.strftime(fmt), allow_clear=False)
    crng = theme.DateRangeField("فترة المقارنة", page, width=280, start=prev_start.strftime(fmt), end=prev_end.strftime(fmt), allow_clear=False)
    kind_dd = ft.Dropdown(label="التقرير", width=260, value=kinds[0][0], options=[ft.dropdown.Option(k, l) for k, l in kinds])
    extras = controls_fn() if controls_fn else {"controls": [], "get": lambda: {}}
    holder = ft.Container()
    state = {"rep": None}

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True))
        page.update()

    def run(e=None):
        try:
            rep = runner(kind_dd.value, rng.start.value, rng.end.value, crng.start.value, crng.end.value, extras["get"]())
            state["rep"] = rep
            holder.content = ft.Column([ft.Text(rep["title"], size=16, weight=ft.FontWeight.BOLD), ft.Text(rep.get("subtitle") or "", size=12, color=theme.TEXT_MUTED), render_table(rep)], spacing=8)
        except Exception as ex:
            holder.content = ft.Text(f"تعذر عرض التقرير: {ex}", color=theme.DANGER)
        page.update()

    def export(e=None):
        if not state["rep"]:
            run()
        if not state["rep"]:
            return
        try:
            co = services.get_company_settings()
            import os
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = ar.export_xlsx(state["rep"], os.path.join(services.downloads_dir(), f"ashour_{kind_dd.value}_{stamp}.xlsx"), getattr(co, "name", "") or "", getattr(page, "_erp_lang", "ar"))
            theme.open_or_download_file(page, path)
            snack(f"تم إنشاء ملف الإكسل: {path}")
        except Exception as ex:
            snack(f"تعذر التصدير: {ex}")

    kind_dd.on_change = run
    row1 = [kind_dd, rng.control] + ([crng.control] if compare else []) + extras["controls"]
    bar = ft.Row(row1 + [ft.FilledButton("عرض", icon=ft.Icons.PLAY_ARROW, on_click=run),
                         ft.OutlinedButton("تصدير Excel", icon=ft.Icons.TABLE_VIEW, on_click=export)], wrap=True, spacing=10, run_spacing=10)
    return ft.Column([theme.page_title(title, subtitle, icon), theme.card(bar), theme.card(holder, expand=True)], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)


# ------------------------------------------------------------------ أرباح وخسائر الفروع
def build_ashour_pnl(page):
    alloc = ft.Switch(label="توزيع مصروفات المركز الرئيسي على الفروع", value=False)
    cache = {}

    def ctl():
        return {"controls": [alloc], "get": lambda: {"alloc": bool(alloc.value)}}

    def runner(kind, f, t, cf, ct, ex):
        res = ar.pnl_compute(f, t, ex["alloc"])
        cache["res"] = res
        if kind == "ratios":
            return ar.pnl_ratios_table(res)
        if kind == "unmapped":
            return ar.pnl_unmapped_table(res)
        return ar.pnl_table(res, kind)

    kinds = [(k, v) for k, v in ar.PNL_VIEWS.items()] + [("ratios", "النسب والمؤشرات"), ("unmapped", "حسابات غير مربوطة")]
    return _screen(page, "أرباح وخسائر الفروع", "مقارنة الفروع مع السنة اللي فاتت والميزانية التقديرية", ft.Icons.STOREFRONT, kinds, runner, ctl, compare=False)


# ------------------------------------------------------------------ مبيعات نقاط البيع
def build_ashour_pos(page):
    branches = ar._branches()
    src = ft.Dropdown(label="المصدر", width=170, value="pos", options=[ft.dropdown.Option("pos", "نقاط البيع فقط"), ft.dropdown.Option("all", "كل المبيعات")])
    br = ft.Dropdown(label="الفرع", width=190, value="", options=[ft.dropdown.Option("", "كل الفروع")] + [ft.dropdown.Option(str(i), n) for i, n in branches])
    gran = ft.Dropdown(label="التقسيم", width=130, value="month", options=[ft.dropdown.Option("year", "سنة"), ft.dropdown.Option("month", "شهر"), ft.dropdown.Option("day", "يوم")])

    def ctl():
        return {"controls": [src, br, gran], "get": lambda: {"src": src.value, "br": int(br.value) if br.value else None, "gran": gran.value}}

    def runner(kind, f, t, cf, ct, ex):
        if kind == "pivot":
            return ar.pos_pivot(f, t, ex["gran"], ex["src"])
        return ar.pos_report(kind, f, t, cf, ct, ex["src"], ex["br"])

    kinds = [("branches", "مقارنة الفروع"), ("daily", "يومي"), ("hourly", "بالساعة"), ("products", "الأصناف"), ("payments", "طرق الدفع"), ("pivot", "جدول الأصناف حسب الفرع")]
    return _screen(page, "مبيعات نقاط البيع", "مقارنة الفروع واليوم والساعة والأصناف وطرق الدفع", ft.Icons.POINT_OF_SALE, kinds, runner, ctl)


# ------------------------------------------------------------------ المشتريات
def build_ashour_purchases(page):
    sups = services.list_suppliers()
    cats = services.list_categories()
    sup = ft.Dropdown(label="المورد", width=200, value="", options=[ft.dropdown.Option("", "كل الموردين")] + [ft.dropdown.Option(str(s.id), s.name) for s in sups])
    cat = ft.Dropdown(label="الفئة", width=200, value="", options=[ft.dropdown.Option("", "كل الفئات")] + [ft.dropdown.Option(str(c.id), c.name) for c in cats])

    def ctl():
        return {"controls": [sup, cat], "get": lambda: {"sup": int(sup.value) if sup.value else None, "cat": int(cat.value) if cat.value else None}}

    def runner(kind, f, t, cf, ct, ex):
        return ar.purchases_report(kind, f, t, cf, ct, ex["sup"], ex["cat"])

    kinds = [("compare", "مقارنة المشتريات"), ("vendors", "مقارنة الموردين (أحسن سعر)"), ("price_changes", "تغيّر الأسعار"), ("ledger", "كشف حساب الموردين")]
    return _screen(page, "تقارير المشتريات", "مقارنة الفترات والموردين وتغيّر الأسعار", ft.Icons.SHOPPING_CART_CHECKOUT, kinds, runner, ctl)


# ------------------------------------------------------------------ العملاء
def build_ashour_customers(page):
    def runner(kind, f, t, cf, ct, ex):
        return ar.customers_report(kind, f, t)

    return _screen(page, "العملاء والتحصيلات", "أرصدة العملاء ونسب التحصيل وأكبر العملاء", ft.Icons.PEOPLE_ALT_OUTLINED, [("balances", "أرصدة العملاء والتحصيلات"), ("top", "أكبر العملاء مبيعًا")], runner, compare=False)


# ------------------------------------------------------------------ الإعدادات
def build_ashour_settings(page):
    cfg = ar.load_config()
    branches = ar._branches()
    start = ft.TextField(label="ساعة بداية يوم العمل (0-23)", width=230, value=str(cfg.get("business_day_start", 0)))
    ho = ft.Dropdown(label="فرع المركز الرئيسي (لتوزيع مصروفاته)", width=300, value=str(cfg.get("head_office_branch_id") or ""),
                     options=[ft.dropdown.Option("", "بدون")] + [ft.dropdown.Option(str(i), n) for i, n in branches])
    fields = {}
    rows = []
    for l in cfg["lines"]:
        if l["type"] == "item":
            tf = ft.TextField(label=l["name"], value=l.get("prefixes", ""), width=360, hint_text="بادئات أكواد الحسابات مفصولة بفاصلة")
            fields[l["code"]] = tf
            rows.append(tf)
    msg = ft.Text("", color=theme.TEXT_MUTED)

    def save(e=None):
        try:
            h = float(start.value or 0)
            if not 0 <= h < 24:
                raise ValueError("ساعة البداية لازم تكون بين 0 و 23")
            new = ar.load_config()
            new["business_day_start"] = h
            new["head_office_branch_id"] = int(ho.value) if ho.value else None
            for l in new["lines"]:
                if l["code"] in fields:
                    l["prefixes"] = fields[l["code"]].value.strip()
            ar.validate_lines(new["lines"])
            ar.save_config(new)
            msg.value = "تم الحفظ"
        except Exception as ex:
            msg.value = f"تعذر الحفظ: {ex}"
        page.update()

    def reset(e=None):
        ar.reset_config()
        for l in ar.DEFAULT_LINES:
            if l["code"] in fields:
                fields[l["code"]].value = l.get("prefixes", "")
        start.value = "0"
        ho.value = ""
        msg.value = "اتعادت الإعدادات الافتراضية"
        page.update()

    body = ft.Column([ft.Text("الحساب بيروح للبند صاحب أطول بادئة مطابقة لكوده (مثلًا 520037 أطول من 52).", size=12, color=theme.TEXT_MUTED),
                      ft.Row([start, ho], wrap=True), ft.Divider(), ft.Text("ربط البنود بالحسابات", weight=ft.FontWeight.BOLD), ft.Row(rows, wrap=True, run_spacing=10),
                      ft.Row([ft.FilledButton("حفظ", icon=ft.Icons.SAVE_OUTLINED, on_click=save), ft.OutlinedButton("رجوع للافتراضي", on_click=reset), msg])], spacing=12)
    return ft.Column([theme.page_title("إعدادات تقارير عاشور", "ربط بنود قائمة الدخل بشجرة الحسابات وبداية يوم العمل", ft.Icons.TUNE), theme.card(body)], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
