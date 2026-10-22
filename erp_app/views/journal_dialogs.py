"""نوافذ أدوات القيود اليومية: القوالب والقيود المتكررة، لصق من Excel، المساعد الذكي، المرفقات، والقيد العكسي.
كل نافذة بتستلم `ctx` من شاشة القيود:
  ctx['collect_lines']()        -> سطور النموذج الحالي (account_id, debit, credit, description, ...) بدون تحقق
  ctx['apply_lines'](lines, replace=True, description=None, reference=None)  -> بتحمّل السطور في النموذج
  ctx['accounts']               -> الحسابات القابلة للترحيل
  ctx['on_reversed'](new_id)    -> بعد القيد العكسي
"""
import datetime

import flet as ft

from .. import journal_tools, services, theme


def _snack(page, msg):
    page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()


def _w(desktop=560):
    mw = theme._page_w()
    return max(260, mw - 64) if mw else desktop


def _open(page, dlg):
    page.overlay.append(dlg); dlg.open = True; page.update()


def _close(page, dlg):
    dlg.open = False; page.update()


def _date(text):
    try:
        return datetime.datetime.strptime((text or "").strip(), "%Y-%m-%d")
    except ValueError:
        return None


def _fmt(d):
    return d.strftime("%Y-%m-%d") if d else "-"


def _line_rows(lines, by_id):
    """عرض مختصر لسطور (حساب + مدين/دائن) داخل نافذة."""
    rows = []
    for l in lines:
        a = by_id.get(l.get("account_id"))
        rows.append(ft.Row([ft.Text(f"{a.code} - {a.name}" if a else f"؟ {l.get('account_text') or ''}", size=12, expand=True,
                                    color=None if a else theme.DANGER),
                            ft.Text(f"{l['debit']:,.2f}" if l["debit"] else "", size=12, width=80, text_align=ft.TextAlign.END),
                            ft.Text(f"{l['credit']:,.2f}" if l["credit"] else "", size=12, width=80, text_align=ft.TextAlign.END)], spacing=6))
    head = ft.Row([ft.Text("الحساب", size=11, color=theme.TEXT_MUTED, expand=True), ft.Text("مدين", size=11, width=80, color=theme.TEXT_MUTED, text_align=ft.TextAlign.END),
                   ft.Text("دائن", size=11, width=80, color=theme.TEXT_MUTED, text_align=ft.TextAlign.END)], spacing=6)
    for r in [head] + rows:
        r._erp_nowrap = True
    return [head] + rows


# ======================================================================= القيد العكسي
def reverse_dialog(page, ctx, entry_id):
    try:
        e = services.get_journal_entry(entry_id)
    except Exception as ex:
        return _snack(page, str(ex))
    if not e:
        return _snack(page, "القيد غير موجود")
    date_f = theme.DateField("تاريخ القيد العكسي", page, width=200, value=datetime.date.today().strftime("%Y-%m-%d"))
    reason = ft.TextField(label="السبب (اختياري)", width=_w(420), max_length=120)
    err = ft.Text("", color=theme.DANGER, visible=False)

    def go(ev):
        try:
            d = _date(date_f.value)
            if not d:
                raise ValueError("اختر تاريخ صحيح")
            new_id = journal_tools.reverse_journal_entry(entry_id, entry_date=d, reason=reason.value or "")
            _close(page, dlg)
            _snack(page, "تم عمل القيد العكسي")
            ctx["on_reversed"](new_id)
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()

    dlg = ft.AlertDialog(modal=True, title=ft.Text(f"قيد عكسي للقيد {e.number}"),
                         content=ft.Column([ft.Text("هيتعمل قيد جديد بنفس الحسابات والأطراف ومراكز التكلفة بس المدين يبقى دائن والعكس، ويتربط بالقيد الأصلي. الأصلي مش بيتمسح.",
                                                    size=12, color=theme.TEXT_MUTED, width=_w(420)), date_f.control, reason, err], tight=True, spacing=10),
                         actions=[ft.TextButton("إلغاء", on_click=lambda ev: _close(page, dlg)),
                                  theme.guard_submit(ft.FilledButton("عمل القيد العكسي", icon=ft.Icons.UNDO, bgcolor=theme.PRIMARY, on_click=go))])
    _open(page, dlg)


# ======================================================================= القوالب والمتكررة
def templates_dialog(page, ctx):
    by_id = {a.id: a for a in ctx["accounts"]}
    tpl_col = ft.Column(spacing=4)
    rec_col = ft.Column(spacing=4)
    name_f = ft.TextField(label="اسم القالب (يتحفظ من القيد الحالي)", width=_w(300))
    err = ft.Text("", color=theme.DANGER, visible=False)

    def save_current(ev):
        try:
            lines = [l for l in ctx["collect_lines"]() if l.get("account_id")]
            journal_tools.save_template(name_f.value, lines, description=ctx["get_header"]()["description"], reference=ctx["get_header"]()["reference"])
            name_f.value = ""; err.visible = False
            refresh(); _snack(page, "اتحفظ القالب")
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()

    def load(t):
        def h(ev):
            _close(page, dlg)
            ctx["apply_lines"](t["lines"], replace=True, description=t["description"], reference=t["reference"])
        return h

    def delete(t):
        def h(ev):
            try:
                journal_tools.delete_template(t["id"]); refresh()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        return h

    def schedule(t):
        def h(ev):
            schedule_dialog(page, t, refresh)
        return h

    def toggle(r):
        def h(ev):
            try:
                journal_tools.save_recurrence(r["template_id"], r["frequency"], r["next_date"], r["end_date"], r["auto_post"], not r["is_active"], recurrence_id=r["id"])
                refresh()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        return h

    def remove(r):
        def h(ev):
            try:
                journal_tools.delete_recurrence(r["id"]); refresh()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        return h

    def run_now(ev):
        try:
            n = len(journal_tools.run_due_recurrences())
            refresh(); _snack(page, f"اتولّد {n} قيد مستحق" if n else "مفيش قيود مستحقة دلوقتي")
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()

    def refresh():
        tpls = journal_tools.list_templates()
        tpl_col.controls = [ft.Text("مفيش قوالب لسه - اكتب قيد واحفظه كقالب", size=12, color=theme.TEXT_MUTED)] if not tpls else []
        for t in tpls:
            total = sum(l["debit"] for l in t["lines"])
            top = ft.Row([ft.Column([ft.Text(t["name"], weight=ft.FontWeight.BOLD, size=13), ft.Text(f"{len(t['lines'])} سطر • {total:,.2f}", size=11, color=theme.TEXT_MUTED)], spacing=0, expand=True)], spacing=6)
            top._erp_nowrap = True
            tpl_col.controls.append(ft.Container(padding=8, border_radius=8, bgcolor=theme.SURFACE_ALT, content=ft.Column([
                top, ft.Row([ft.FilledButton("تحميل", icon=ft.Icons.DOWNLOAD, on_click=load(t), bgcolor=theme.PRIMARY),
                             ft.OutlinedButton("جدولة", icon=ft.Icons.EVENT_REPEAT, on_click=schedule(t)),
                             ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip="حذف القالب", on_click=delete(t))], spacing=6, wrap=True)], spacing=4)))
        recs = journal_tools.list_recurrences()
        rec_col.controls = [ft.Text("مفيش قيود متكررة", size=12, color=theme.TEXT_MUTED)] if not recs else []
        for r in recs:
            state = "شغّال" if r["is_active"] else "موقوف"
            mode = "ترحيل تلقائي" if r["auto_post"] else "مسودة للمراجعة"
            bits = [ft.Text(f"{r['template']} • {r['frequency_label']} • {mode}", weight=ft.FontWeight.BOLD, size=12),
                    ft.Text(f"التالي: {_fmt(r['next_date'])} • اتنفّذ {r['runs_count']} مرة • {state}" + (f" • ينتهي {_fmt(r['end_date'])}" if r["end_date"] else ""), size=11, color=theme.TEXT_MUTED)]
            if r["last_error"]:
                bits.append(ft.Text(f"آخر خطأ: {r['last_error']}", size=11, color=theme.DANGER))
            rec_col.controls.append(ft.Container(padding=8, border_radius=8, bgcolor=theme.SURFACE_ALT, content=ft.Column([
                ft.Column(bits, spacing=0),
                ft.Row([ft.OutlinedButton("إيقاف" if r["is_active"] else "تشغيل", icon=ft.Icons.PAUSE if r["is_active"] else ft.Icons.PLAY_ARROW, on_click=toggle(r)),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip="حذف الجدولة", on_click=remove(r))], spacing=6, wrap=True)], spacing=4)))
        page.update()

    content = ft.Column([
        ft.Text("القوالب", size=15, weight=ft.FontWeight.BOLD),
        ft.Row([name_f, ft.OutlinedButton("حفظ القيد الحالي كقالب", icon=ft.Icons.SAVE_OUTLINED, on_click=save_current)], spacing=8, wrap=True),
        tpl_col, ft.Divider(),
        ft.Row([ft.Text("القيود المتكررة", size=15, weight=ft.FontWeight.BOLD), ft.TextButton("تنفيذ المستحق الآن", icon=ft.Icons.PLAY_CIRCLE_OUTLINE, on_click=run_now)], spacing=8, wrap=True),
        ft.Text("بتتولّد تلقائيًا من السيرفر عند الاستحقاق (كل نص ساعة). لو فترة مقفولة أو حساب فيه مشكلة بتقف وتظهر رسالة الخطأ هنا.", size=11, color=theme.TEXT_MUTED, width=_w(520)),
        rec_col, err,
    ], spacing=8, scroll=ft.ScrollMode.AUTO, width=_w(560), height=480)
    content._erp_nocap = True
    dlg = ft.AlertDialog(modal=True, title=ft.Text("القوالب والقيود المتكررة"), content=content,
                         actions=[ft.TextButton("إغلاق", on_click=lambda ev: _close(page, dlg))])
    _open(page, dlg)
    refresh()


def schedule_dialog(page, t, on_done):
    freq = ft.Dropdown(label="التكرار", width=_w(260), value="monthly", options=[ft.dropdown.Option(k, v) for k, v in journal_tools.FREQUENCIES.items()])
    start = theme.DateField("أول تنفيذ", page, width=200, value=datetime.date.today().strftime("%Y-%m-%d"))
    end = theme.DateField("ينتهي في (اختياري)", page, width=200, value=None)
    auto = ft.Checkbox(label="ترحيل تلقائي (لو مش متعلّم بيتولّد مسودة للمراجعة)", value=True)
    err = ft.Text("", color=theme.DANGER, visible=False)

    def go(ev):
        try:
            s = _date(start.value)
            if not s:
                raise ValueError("اختر تاريخ أول تنفيذ")
            e = _date(end.value) if (end.value or "").strip() else None
            journal_tools.save_recurrence(t["id"], freq.value, s, e, auto.value)
            _close(page, dlg); on_done()
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()

    dlg = ft.AlertDialog(modal=True, title=ft.Text(f"جدولة «{t['name']}»"),
                         content=ft.Column([freq, start.control, end.control, auto, err], tight=True, spacing=10, width=_w(360)),
                         actions=[ft.TextButton("إلغاء", on_click=lambda ev: _close(page, dlg)), ft.FilledButton("حفظ الجدولة", bgcolor=theme.PRIMARY, on_click=go)])
    _open(page, dlg)


# ======================================================================= لصق من Excel
def paste_dialog(page, ctx):
    by_id = {a.id: a for a in ctx["accounts"]}
    box = ft.TextField(label="الصق هنا (من Excel: حساب | بيان | مدين | دائن)", multiline=True, min_lines=5, max_lines=8, width=_w(560), text_size=12)
    preview = ft.Column(spacing=2)
    warns = ft.Column(spacing=2)
    err = ft.Text("", color=theme.DANGER, visible=False)
    state = {"lines": None}
    use_btn = ft.FilledButton("استخدام السطور في القيد", icon=ft.Icons.CHECK, bgcolor=theme.PRIMARY, visible=False)

    def show(res):
        state["lines"] = res["lines"]
        preview.controls = _line_rows(res["lines"], by_id)
        warns.controls = [ft.Text("• " + w, size=11, color=theme.WARNING_TEXT) for w in res["warnings"]]
        td = sum(l["debit"] for l in res["lines"]); tc = sum(l["credit"] for l in res["lines"])
        preview.controls.append(ft.Text(f"الإجمالي: مدين {td:,.2f} | دائن {tc:,.2f}", size=12, weight=ft.FontWeight.BOLD))
        use_btn.visible = True; err.visible = False; page.update()

    def analyze(ev):
        try:
            show(journal_tools.parse_pasted_lines(box.value or "", ctx["accounts"]))
        except Exception as ex:
            use_btn.visible = False; preview.controls = []; warns.controls = []
            err.value = str(ex); err.visible = True; page.update()

    async def from_file(ev):
        try:
            path = await theme.pick_file(page, "اختر ملف Excel أو CSV", ["xlsx", "csv"])
            if path:
                show(journal_tools.parse_excel_lines(path, ctx["accounts"]))
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()

    def use(ev):
        _close(page, dlg)
        ctx["apply_lines"](state["lines"], replace=True)

    use_btn.on_click = use
    content = ft.Column([
        ft.Text("الصق الصفوف من Excel (الأعمدة: الحساب بالكود أو الاسم، البيان، مدين، دائن) أو اختار ملف. صف العناوين اختياري. السطور اللي حسابها مش معروف هتتحمّل فاضية عشان تختار حسابها بإيدك.",
                size=12, color=theme.TEXT_MUTED, width=_w(560)),
        box,
        ft.Row([ft.FilledButton("تحليل", icon=ft.Icons.FACT_CHECK_OUTLINED, on_click=analyze, bgcolor=theme.PRIMARY),
                ft.OutlinedButton("اختيار ملف Excel / CSV", icon=ft.Icons.UPLOAD_FILE, on_click=from_file)], spacing=8, wrap=True),
        err, warns, preview,
    ], spacing=8, scroll=ft.ScrollMode.AUTO, width=_w(580), height=440)
    content._erp_nocap = True
    dlg = ft.AlertDialog(modal=True, title=ft.Text("لصق سطور من Excel"), content=content,
                         actions=[ft.TextButton("إلغاء", on_click=lambda ev: _close(page, dlg)), use_btn])
    _open(page, dlg)


# ======================================================================= المساعد الذكي
def ai_dialog(page, ctx):
    by_id = {a.id: a for a in ctx["accounts"]}
    desc = ft.TextField(label="اوصف العملية بالعربي (مثلاً: دفعنا إيجار المقر ٥٠٠٠ نقدًا)", multiline=True, min_lines=2, max_lines=4, width=_w(560))
    amount = ft.TextField(label="المبلغ (اختياري)", width=180, keyboard_type=ft.KeyboardType.NUMBER)
    status = ft.Text("", size=12)
    preview = ft.Column(spacing=2)
    err = ft.Text("", color=theme.DANGER, visible=False)
    state = {"res": None}
    use_btn = ft.FilledButton("استخدام الاقتراح", icon=ft.Icons.CHECK, bgcolor=theme.PRIMARY, visible=False)
    key_f = ft.TextField(label="مفتاح Anthropic API", password=True, can_reveal_password=True, width=_w(420), hint_text="يتحفظ على السيرفر فقط")
    model_f = ft.TextField(label="النموذج", width=220, value=journal_tools.get_ai_config()["model"])
    on_sw = ft.Switch(label="تفعيل المساعد الذكي (Claude)", value=journal_tools.get_ai_config()["enabled"])
    cfg_msg = ft.Text("", size=11, color=theme.TEXT_MUTED)

    def refresh_status():
        st = journal_tools.ai_status()
        status.value = ("المساعد الذكي (Claude) مفعّل - بيتبعت له الوصف وأسماء الحسابات بس." if st["enabled"]
                        else "المساعد الذكي مش مفعّل - الاقتراح هيكون من قيودك السابقة بس. فعّله من الإعدادات تحت.")
        status.color = theme.SUCCESS if st["enabled"] else theme.TEXT_MUTED
        cfg_msg.value = "المفتاح محفوظ ✓" if st["has_key"] else "لسه مفيش مفتاح"

    def suggest(ev):
        try:
            amt = float((amount.value or "0").replace(",", "")) if (amount.value or "").strip() else None
        except ValueError:
            err.value = "المبلغ غير صحيح"; err.visible = True; page.update(); return
        err.visible = False; use_btn.visible = False; preview.controls = [ft.ProgressRing(width=20, height=20)]; page.update()
        try:
            res = journal_tools.suggest_entry(desc.value or "", amt)
        except Exception as ex:
            preview.controls = []; err.value = str(ex); err.visible = True; page.update(); return
        state["res"] = res
        notes = [ft.Text(f"المصدر: {res['source']}", size=11, color=theme.TEXT_MUTED)]
        if res.get("explanation"):
            notes.append(ft.Text(res["explanation"], size=12))
        if res.get("warning"):
            notes.append(ft.Text(res["warning"], size=11, color=theme.WARNING_TEXT))
        notes.append(ft.Text("راجع الحسابات والمبالغ كويس قبل الترحيل - ده اقتراح مش قيد نهائي.", size=11, color=theme.WARNING_TEXT))
        preview.controls = notes + _line_rows(res["lines"], by_id)
        use_btn.visible = True; page.update()

    def use(ev):
        r = state["res"]
        _close(page, dlg)
        ctx["apply_lines"](r["lines"], replace=True, description=r.get("description") or (desc.value or "").strip()[:200])

    def save_cfg(ev):
        try:
            journal_tools.save_ai_config(on_sw.value, key_f.value, model_f.value)
            key_f.value = ""; refresh_status(); cfg_msg.value = "اتحفظت الإعدادات ✓"; page.update()
        except Exception as ex:
            cfg_msg.value = str(ex); page.update()

    use_btn.on_click = use
    refresh_status()
    content = ft.Column([
        status, desc, ft.Row([amount, ft.FilledButton("اقترح قيد", icon=ft.Icons.AUTO_AWESOME, on_click=suggest, bgcolor=theme.PRIMARY)], spacing=8, wrap=True),
        err, preview, ft.Divider(),
        ft.ExpansionTile(title=ft.Text("إعدادات المساعد الذكي", size=13), dense=True, controls=[
            ft.Container(padding=ft.Padding(left=8, right=8, top=0, bottom=8), content=ft.Column([
                on_sw, key_f, model_f, ft.Row([ft.OutlinedButton("حفظ الإعدادات", icon=ft.Icons.SAVE_OUTLINED, on_click=save_cfg), cfg_msg], spacing=8, wrap=True)], spacing=8))]),
    ], spacing=8, scroll=ft.ScrollMode.AUTO, width=_w(580), height=440)
    content._erp_nocap = True
    dlg = ft.AlertDialog(modal=True, title=ft.Text("مساعد القيود الذكي"), content=content,
                         actions=[ft.TextButton("إغلاق", on_click=lambda ev: _close(page, dlg)), use_btn])
    _open(page, dlg)


# ======================================================================= المرفقات
def attachments_dialog(page, ctx, entry_id):
    try:
        e = services.get_journal_entry(entry_id)
    except Exception as ex:
        return _snack(page, str(ex))
    col = ft.Column(spacing=6)
    err = ft.Text("", color=theme.DANGER, visible=False)

    def refresh():
        rows = journal_tools.list_attachments(entry_id)
        col.controls = [ft.Text("مفيش مرفقات لسه", size=12, color=theme.TEXT_MUTED)] if not rows else []
        for a in rows:
            def open_(ev, p=a["file_path"]):
                theme.open_or_download_file(page, p)

            def del_(ev, i=a["id"]):
                try:
                    journal_tools.delete_attachment(i); refresh()
                except Exception as ex:
                    err.value = str(ex); err.visible = True; page.update()
            row = ft.Row([ft.Icon(ft.Icons.ATTACH_FILE, size=16, color=theme.PRIMARY), ft.TextButton(a["file_name"], on_click=open_),
                          ft.Text(a["uploaded_at"].strftime("%Y-%m-%d %H:%M") if a["uploaded_at"] else "", size=11, color=theme.TEXT_MUTED),
                          ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, icon_size=18, on_click=del_)], spacing=6, wrap=True)
            col.controls.append(row)
        page.update()

    async def add(ev):
        try:
            path = await theme.pick_file(page, "اختر المستند الداعم", ["pdf", "png", "jpg", "jpeg", "xlsx", "docx"], max_mb=15)
            if path:
                journal_tools.attach_file(entry_id, path); err.visible = False; refresh()
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()

    dlg = ft.AlertDialog(modal=True, title=ft.Text(f"مرفقات القيد {e.number if e else ''}"),
                         content=ft.Column([ft.OutlinedButton("إضافة مرفق", icon=ft.Icons.ADD, on_click=add), err, col], tight=True, spacing=10, width=_w(460), scroll=ft.ScrollMode.AUTO),
                         actions=[ft.TextButton("إغلاق", on_click=lambda ev: _close(page, dlg))])
    _open(page, dlg)
    refresh()
