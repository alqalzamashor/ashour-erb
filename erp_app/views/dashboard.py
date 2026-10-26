import datetime
import flet as ft
from .. import services, theme, insights, alerts, field_access


def _money(v):
    return "—" if v is None else "\u200e" + f"{float(v or 0):,.2f}"       # LRM: علشان علامة السالب تفضل قدّام الرقم في العربي


def _pct(v):
    return "—" if v is None else "\u200e" + f"{float(v or 0):.1f}%"


def _spark(values, color, h=30):
    """رسم مصغّر (أعمدة صغيرة) لآخر شهور - بيدّي اتجاه الرقم في لمحة."""
    vals = [float(v or 0) for v in values][-8:]
    if len(vals) < 2:
        return ft.Container(height=h)
    mx = max(abs(v) for v in vals) or 1
    return ft.Row([ft.Container(width=9, height=max(3, int(h * abs(v) / mx)), border_radius=3,
                                bgcolor=ft.Colors.with_opacity(0.95 if k == len(vals) - 1 else 0.28, color)) for k, v in enumerate(vals)],
                  spacing=4, vertical_alignment=ft.CrossAxisAlignment.END, height=h)


def _delta_chip(delta):
    """شريحة التغيّر عن الفترة السابقة: (نسبة، جيد؟). أخضر للتحسّن وأحمر للتراجع."""
    if not delta or delta[0] is None:
        return None
    pct, good = delta
    col = theme.TEXT_MUTED if good is None else (theme.SUCCESS if good else theme.DANGER)
    ic = [] if abs(pct) < 0.05 else [ft.Icon(ft.Icons.ARROW_UPWARD if pct > 0 else ft.Icons.ARROW_DOWNWARD, size=12, color=col)]
    return ft.Container(ft.Row(ic + [ft.Text(f"\u200e{abs(pct):.1f}%", size=11, weight=ft.FontWeight.W_700, color=col)], spacing=2, tight=True),
                        bgcolor=ft.Colors.with_opacity(0.12, col), border_radius=20, padding=ft.Padding.symmetric(horizontal=8, vertical=2))


def _card(title, value, icon, color, on_click=None, subtitle="اضغط للتفاصيل", delta=None, spark=None, spark_space=False):
    """بطاقة مؤشر موحّدة: أيقونة في دائرة ملوّنة + العنوان، الرقم كبير، شريحة التغيّر + رسم مصغّر، وشريط لوني رفيع في الأسفل."""
    head = ft.Row([
        ft.Container(ft.Icon(icon, color=color, size=20), width=38, height=38, border_radius=12, alignment=ft.Alignment(0, 0), bgcolor=ft.Colors.with_opacity(0.13, color)),
        ft.Text(title, size=13, color=theme.TEXT_MUTED, weight=ft.FontWeight.W_600, expand=True, max_lines=2),
    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    foot = [c for c in (_delta_chip(delta), ft.Text(subtitle, size=11, color=theme.TEXT_MUTED, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS) if subtitle else None) if c is not None]
    col = [head, ft.Text(value, size=24, weight=ft.FontWeight.W_800, color=theme.TEXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS), ft.Row(foot, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)]
    if spark:
        col.append(_spark(spark, color))
    elif spark_space:
        col.append(ft.Container(height=30))
    return ft.Container(content=ft.Column(col, spacing=8), padding=ft.Padding(left=14, right=14, top=14, bottom=12), border_radius=theme.RADIUS, bgcolor=theme.CARD_BG,
                        border=ft.border.Border(*(ft.border.BorderSide(1, theme.BORDER_LIGHT) for _ in range(3)), ft.border.BorderSide(3, ft.Colors.with_opacity(0.85, color))),
                        shadow=ft.BoxShadow(spread_radius=0, blur_radius=16, color=ft.Colors.with_opacity(0.07, "#0F2F27"), offset=ft.Offset(0, 4)),
                        on_click=on_click, ink=True if on_click else False)


def _grid(cards, lg=3):
    """شبكة متجاوبة: 4 في الصف على الشاشة الكبيرة، 2 على المتوسطة، 1 على الموبايل."""
    for c in cards:
        c.col = {"xs": 6, "sm": 6, "lg": lg}
    return ft.ResponsiveRow(cards, spacing=12, run_spacing=12)


def _section(title, subtitle=""):
    bar = ft.Container(width=4, height=34 if subtitle else 20, bgcolor=theme.PRIMARY, border_radius=3)
    txt = [ft.Text(title, size=16, weight=ft.FontWeight.W_800, color=theme.TEXT)]
    if subtitle:
        txt.append(ft.Text(subtitle, size=11.5, color=theme.TEXT_MUTED))
    return ft.Row([bar, ft.Column(txt, spacing=1)], spacing=10)


def _bar_row(label,value,max_value,number,color=theme.PRIMARY,height=14):
    """شريط أفقي بعرض مرن (بياخد المساحة المتاحة بدل عرض ثابت) - الرقم على الطرف."""
    ratio=min(abs(float(value or 0))/(abs(float(max_value or 0)) or 1),1)
    a=max(1,int(ratio*1000)); b=1000-a
    fill=ft.Container(expand=a,height=height,border_radius=7,bgcolor=color)
    inner=[fill]+([ft.Container(expand=b,height=height)] if b>0 else [])
    return ft.Row([
        ft.Container(width=120,content=ft.Text(label,size=12,max_lines=1,overflow=ft.TextOverflow.ELLIPSIS,color=theme.TEXT)),
        ft.Container(expand=True,height=height,border_radius=7,bgcolor=ft.Colors.with_opacity(0.10,color),content=ft.Row(inner,spacing=0)),
        ft.Container(width=100,content=ft.Text(number,size=12,weight=ft.FontWeight.W_700,text_align=ft.TextAlign.END,color=theme.TEXT)),
    ],spacing=10,vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _legend(items):
    return ft.Row([ft.Row([ft.Container(width=10,height=10,border_radius=3,bgcolor=c),ft.Text(t,size=11.5,color=theme.TEXT_MUTED)],spacing=5) for t,c in items],spacing=16,wrap=True)


def _monthly_chart(rows,on_month=None):
    if not rows:
        return ft.Text("لا توجد بيانات شهرية في الفترة المحددة",color=theme.TEXT_MUTED)
    maxv=max([abs(max(float(r['revenue'] or 0),float(r['expense'] or 0),float(r['profit'] or 0))) for r in rows] or [1]) or 1
    H=150
    cols=[]
    for r in rows:
        vals=[('المبيعات',r['revenue'],theme.PRIMARY),('المصروفات',r['expense'],theme.DANGER)]+([('الربح',r['profit'],theme.SUCCESS if r['profit']>=0 else theme.WARNING)] if r['profit'] is not None else [])
        bars=[]
        for label,val,color in vals:
            ratio=min(abs(float(val or 0))/maxv,1)
            bars.append(ft.Column([
                ft.Text(_money(val).replace('.00',''),size=9.5,color=theme.TEXT_MUTED,text_align=ft.TextAlign.CENTER),
                ft.Container(width=26,height=H,alignment=ft.Alignment(0,1),border_radius=7,bgcolor=ft.Colors.with_opacity(0.06,color),
                             content=ft.Container(width=26,height=max(4,int(H*ratio)),bgcolor=color,border_radius=7),tooltip=f"{label}: {_money(val)}"),
            ],spacing=3,horizontal_alignment=ft.CrossAxisAlignment.CENTER))
        cols.append(ft.Container(content=ft.Column([ft.Row(bars,spacing=5,vertical_alignment=ft.CrossAxisAlignment.END),ft.Text(r['label'],size=11,weight=ft.FontWeight.W_700,color=theme.TEXT)],horizontal_alignment=ft.CrossAxisAlignment.CENTER,spacing=6),padding=8,border_radius=10,ink=True,on_click=(lambda e,x=r: on_month(x) if on_month else None)))
    leg=_legend([('المبيعات',theme.PRIMARY),('المصروفات',theme.DANGER)]+([('الربح',theme.SUCCESS)] if rows[0]['profit'] is not None else []))
    return ft.Column([leg,ft.Row(cols,scroll=ft.ScrollMode.AUTO,spacing=14)],spacing=10)


def _open_details(page,title,columns,rows):
    cells=[]
    for row in rows:
        cells.append(ft.DataRow(cells=[ft.DataCell(ft.Text(str(row.get(k,'')))) for k,_ in columns]))
    table=ft.DataTable(columns=[ft.DataColumn(ft.Text(label)) for _,label in columns],rows=cells,heading_row_height=42)

    def close_dlg(e=None):
        dlg.open=False
        page.update()

    dlg=ft.AlertDialog(modal=True,title=ft.Text(title),content=ft.Container(content=theme.h_scroll(table),width=1000,height=520),actions=[ft.TextButton("إغلاق",on_click=close_dlg)])
    page.overlay.append(dlg)
    dlg.open=True
    page.update()


SEV_COLOR = {"high": theme.DANGER, "medium": theme.WARNING, "low": theme.TEXT_MUTED}
SEV_LABEL = {"high": "عاجل", "medium": "مهم", "low": "للعلم"}
_PCT_KEYS = {"net_margin_pct", "gross_margin_pct"}
_INT_KEYS = {"sales_count"}


def _fmt_metric(key, v):
    if v is None:
        return "—"
    return _pct(v) if key in _PCT_KEYS else (f"{int(round(v)):,}" if key in _INT_KEYS else _money(v))


def _compare_section(cmp):
    rows = []
    for r in cmp["rows"]:
        col = theme.TEXT_MUTED if r["good"] is None else (theme.SUCCESS if r["good"] else theme.DANGER)
        d = r["delta"]
        arrow = ""
        pct = "—" if r["delta_pct"] is None else f"{r['delta_pct']:+.1f}%"
        rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(r["label"], size=12)), ft.DataCell(ft.Text(_fmt_metric(r["key"], r["current"]), size=12, weight=ft.FontWeight.BOLD)),
                                      ft.DataCell(ft.Text(_fmt_metric(r["key"], r["previous"]), size=12)),
                                      ft.DataCell(ft.Row(([] if d is None or abs(d) < 0.005 else [ft.Icon(ft.Icons.ARROW_UPWARD if d > 0 else ft.Icons.ARROW_DOWNWARD, size=13, color=col)]) + [ft.Text("—" if d is None else _fmt_metric(r["key"], abs(d)), size=12, color=col)], spacing=3, tight=True)),
                                      ft.DataCell(ft.Text(pct, size=12, color=col, weight=ft.FontWeight.BOLD))]))
    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD)) for x in ["المؤشر", "الفترة الحالية", "الفترة المقارنة", "الفرق", "التغيّر %"]], rows=rows, heading_row_height=38, data_row_min_height=34)
    pr = cmp["prev_range"]
    return ft.Column([_section("مقارنة الفترات", f"مقارنة بـ {pr[0]:%Y-%m-%d} → {pr[1]:%Y-%m-%d}" if pr else ""), theme.h_scroll(table)], spacing=8)


def _cash_section(c):
    cards = _grid([
        _card("رصيد النقدية أول الفترة", _money(c["opening"]), ft.Icons.ACCOUNT_BALANCE, theme.TEXT_MUTED, subtitle=""),
        _card("تشغيلي", _money(c["operating"]), ft.Icons.STOREFRONT, theme.SUCCESS if c["operating"] >= 0 else theme.DANGER, subtitle="صافي من الأنشطة التشغيلية"),
        _card("استثماري", _money(c["investing"]), ft.Icons.BUSINESS_CENTER, theme.SECONDARY, subtitle="أصول واستثمارات"),
        _card("تمويلي", _money(c["financing"]), ft.Icons.SAVINGS, theme.PRIMARY, subtitle="قروض ورأس مال"),
        _card("رصيد النقدية آخر الفترة", _money(c["closing"]), ft.Icons.PAYMENTS, theme.SUCCESS if c["closing"] >= 0 else theme.DANGER, subtitle=f"صافي التغيّر {_money(c['net'])}"),
    ], lg=4)
    for k_, w_ in zip(cards.controls, (6, 4, 4, 4, 6)):
        k_.col = {"xs": 6, "sm": 6, "lg": w_}
    cards.controls.insert(1, cards.controls.pop(4))        # أول الفترة وآخرها جنب بعض فوق، والأنشطة التلاتة تحتهم
    mx = max([abs(m["net"]) for m in c["months"]] or [1]) or 1
    bars = ft.Column([_bar_row(m["label"], m["net"], mx, _money(m["net"]), theme.SUCCESS if m["net"] >= 0 else theme.DANGER) for m in c["months"]], spacing=5)
    warn = ft.Text(f"فرق غير مفسَّر في التدفقات: {_money(c['unexplained'])} - راجع تصنيف الحسابات في شجرة الحسابات.", size=11, color=theme.WARNING) if abs(c.get("unexplained") or 0) > 0.5 else ft.Container()
    return ft.Column([_section("التدفق النقدي", "صافي حركة النقدية والبنوك حسب النشاط، وصافي التغيّر الشهري"), cards, bars, warn], spacing=10)


def _integrity_strip(page):
    """شارة سلامة الدفاتر: لو فيه أخطاء/تحذيرات بتظهر بالأحمر/البرتقالي مع تفاصيلها، وإلا بتظهر "سليمة" بالأخضر."""
    from .. import data_integrity
    try:
        r = data_integrity.quick_summary()
    except Exception:      # noqa: BLE001 - الشارة مش لازم تعطّل الرئيسية
        return None
    if r is None:
        return None
    if not r["items"]:
        return theme.card(ft.Row([ft.Icon(ft.Icons.VERIFIED_OUTLINED, color=theme.SUCCESS), ft.Text("سلامة الدفاتر: سليمة (الميزان متوازن، القيود مكتملة، المخزون مطابق)", size=13)], spacing=8))
    color = theme.DANGER if r["errors"] else theme.WARNING
    return theme.card(ft.Row([ft.Icon(ft.Icons.GPP_MAYBE_OUTLINED, color=color),
                              ft.Text(f"سلامة الدفاتر: {r['errors']} خطأ، {r['warnings']} تحذير", size=13, weight=ft.FontWeight.BOLD, color=color), ft.Container(expand=True),
                              ft.TextButton("التفاصيل", on_click=lambda e: _open_details(page, "فحص سلامة الدفاتر", [("title", "الفحص"), ("count", "العدد"), ("sev", "الأهمية")],
                                                                                         [{"title": t, "count": n, "sev": "خطأ" if sv == "error" else "تحذير"} for t, n, sv in r["items"]]))], spacing=8))


def _alerts_strip(page, items):
    if not items:
        return theme.card(ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=theme.SUCCESS), ft.Text("مفيش تنبيهات حاليًا", size=13)], spacing=8))
    counts = {}
    for a in items:
        counts[a["kind"]] = counts.get(a["kind"], 0) + 1

    def open_kind(kind=None):
        rows = [a for a in items if kind in (None, a["kind"])]
        _open_details(page, "التنبيهات" + (f" - {alerts.KINDS[kind]}" if kind else ""), [("sev", "الأهمية"), ("kind", "النوع"), ("title", "البند"), ("detail", "التفاصيل")],
                      [{"sev": SEV_LABEL[a["severity"]], "kind": alerts.KINDS[a["kind"]], "title": a["title"], "detail": a["detail"]} for a in rows[:300]])
    chips = [ft.Container(ft.Row([ft.Text(alerts.KINDS[k], size=12), ft.Container(ft.Text(str(n), size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE), bgcolor=theme.DANGER if k in ("low", "limit") else theme.WARNING, border_radius=10, padding=ft.Padding.symmetric(horizontal=8, vertical=1))], spacing=6),
                          padding=10, border_radius=10, bgcolor=ft.Colors.with_opacity(0.06, theme.WARNING), ink=True, on_click=lambda e, k=k: open_kind(k)) for k, n in counts.items()]
    top = [ft.Row([ft.Container(width=8, height=8, border_radius=4, bgcolor=SEV_COLOR[a["severity"]]), ft.Text(f"{a['title']}: {a['detail']}", size=11.5, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)], spacing=6) for a in items[:2]]
    return theme.card(ft.Column([ft.Row([ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE_OUTLINED, color=theme.WARNING), ft.Text(f"تنبيهات ذكية ({len(items)})", weight=ft.FontWeight.BOLD), ft.Container(expand=True),
                                         ft.TextButton("عرض الكل", on_click=lambda e: open_kind(None))]), ft.Row(chips, wrap=True, spacing=8)] + top, spacing=8))


from . import onboarding as onboarding_view


def build_dashboard(page: ft.Page, user=None):
    branches=services.list_branches(True); allowed=services.user_branch_ids(user)
    if allowed: branches=[b for b in branches if b.id in allowed]
    centers=services.list_cost_centers(True); allowed_cc=services.user_cost_center_ids(user)
    if allowed_cc: centers=[c for c in centers if c.id in allowed_cc]
    now=datetime.datetime.now()
    branch_dd=ft.Dropdown(label="الفرع",width=210,dense=True,text_size=13,options=[ft.dropdown.Option(str(b.id),f"{b.code} - {b.name}") for b in branches],value=str(branches[0].id) if branches else None)
    cc_dd=ft.Dropdown(label="مركز التكلفة",width=210,dense=True,text_size=13,options=[ft.dropdown.Option(str(c.id),f"{c.code} - {c.name}") for c in centers],value=None)
    rng=theme.DateRangeField("الفترة",page,width=290,start=f"{now.year}-01-01",end=now.strftime("%Y-%m-%d"))
    df,dt=rng.start,rng.end
    cmp_dd=ft.Dropdown(label="مقارنة بـ",width=230,dense=True,text_size=13,options=[ft.dropdown.Option(k,v) for k,v in insights.MODES.items()],value="prev")
    status=ft.Text("",color=theme.DANGER)
    root=ft.Column(expand=True,scroll=ft.ScrollMode.AUTO,spacing=14)
    state={}

    def parse(v): return datetime.datetime.strptime(v.strip(),"%Y-%m-%d") if v and v.strip() else None
    def selected_id(dd): return int(dd.value) if dd.value else None

    def refresh(e=None):
        try:
            data=services.executive_dashboard(parse(df.value),parse(dt.value),selected_id(branch_dd),selected_id(cc_dd)); state.clear();state.update(data)
            k=data['kpis']; inv=data['inventory']; aging=data['aging']
            def detail_kpi(title,kind):
                if kind=='revenue': rows=[{'البند':'الإيرادات','القيمة':_money(k['revenue'])}]
                elif kind=='expense': rows=[{'البند':'المصروفات','القيمة':_money(k['expense'])}]
                elif kind=='profit': rows=[{'البند':'صافي الربح','القيمة':_money(k['profit'])},{'البند':'هامش صافي الربح','القيمة':_pct(k['net_margin_pct'])}]
                elif kind=='gross': rows=[{'البند':'مجمل الربح','القيمة':_money(k['gross_profit'])},{'البند':'هامش إجمالي','القيمة':_pct(k['gross_margin_pct'])}]
                else: rows=[]
                _open_details(page,title,[('البند','البند'),('القيمة','القيمة')],rows)
            show_profit=k['profit'] is not None
            try:
                _cm=insights.compare(parse(df.value),parse(dt.value),cmp_dd.value if cmp_dd.value and cmp_dd.value!='none' else 'prev',selected_id(branch_dd),selected_id(cc_dd)) if parse(df.value) and parse(dt.value) else None
            except Exception:
                _cm=None
            _dl={r['key']:(r['delta_pct'],r['good']) for r in (_cm['rows'] if _cm else [])}
            _mo=data['monthly']
            _sp=lambda f:[x[f] for x in _mo if x.get(f) is not None]
            kpis=_grid([
                _card("إجمالي المبيعات",_money(k['revenue']),ft.Icons.RECEIPT_LONG,theme.PRIMARY,lambda e:detail_kpi("تفاصيل المبيعات","revenue"),"مقارنة بالفترة السابقة" if _dl.get('revenue') and _dl['revenue'][0] is not None else "اضغط للتفاصيل",_dl.get('revenue'),_sp('revenue')),
                _card("المصروفات",_money(k['expense']),ft.Icons.TRENDING_DOWN,theme.DANGER,lambda e:detail_kpi("تفاصيل المصروفات","expense"),"مقارنة بالفترة السابقة" if _dl.get('expense') and _dl['expense'][0] is not None else "اضغط للتفاصيل",_dl.get('expense'),_sp('expense')),
            ]+([
                _card("صافي الربح",_money(k['profit']),ft.Icons.ACCOUNT_BALANCE_WALLET,theme.SUCCESS if k['profit']>=0 else theme.DANGER,lambda e:detail_kpi("تفاصيل الربح","profit"),"مقارنة بالفترة السابقة" if _dl.get('profit') and _dl['profit'][0] is not None else "اضغط للتفاصيل",_dl.get('profit'),_sp('profit')),
                _card("مجمل الربح",_money(k['gross_profit']),ft.Icons.INSIGHTS,theme.SECONDARY,lambda e:detail_kpi("تفاصيل مجمل الربح","gross"),"مقارنة بالفترة السابقة" if _dl.get('gross_profit') and _dl['gross_profit'][0] is not None else "اضغط للتفاصيل",_dl.get('gross_profit'),None,True),
            ] if show_profit else []))
            ratios=_grid(([
                _card("هامش صافي الربح",_pct(k['net_margin_pct']),ft.Icons.PERCENT,theme.SUCCESS,lambda e:detail_kpi("نسبة الربحية","profit"),"صافي الربح ÷ الإيرادات"),
                _card("هامش الربح الإجمالي",_pct(k['gross_margin_pct']),ft.Icons.SHOW_CHART,theme.SECONDARY,lambda e:detail_kpi("الهامش الإجمالي","gross"),"مجمل الربح ÷ الإيرادات"),
                ] if show_profit else [])+[
                _card("نسبة المصروفات",_pct(k['expense_ratio_pct']),ft.Icons.DATA_USAGE,theme.WARNING,lambda e:detail_kpi("نسبة المصروفات","expense"),"المصروفات ÷ الإيرادات"),
                _card("الذمم المدينة",_money(aging['total']),ft.Icons.PENDING_ACTIONS,theme.WARNING,lambda e:_open_details(page,"أعمار الذمم المدينة",[("party","العميل"),("number","الفاتورة"),("bucket","العمر"),("days","الأيام"),("due","المستحق")],[{'party':x['party'],'number':x['number'],'bucket':x['bucket'],'days':x['days'],'due':_money(x['due'])} for x in aging['rows']])),
            ])
            extra=[]
            try:
                if services.user_has_action(services._get_user(),'alerts','view'):
                    extra.append(_alerts_strip(page,alerts.compute(selected_id(branch_dd))))
            except Exception as ex_:
                extra.append(ft.Text('تعذر حساب التنبيهات: '+str(ex_),size=11,color=theme.TEXT_MUTED))
            cmp_block=ft.Container()
            try:
                if cmp_dd.value and cmp_dd.value!='none' and parse(df.value) and parse(dt.value):
                    cmp_block=theme.card(_compare_section(insights.compare(parse(df.value),parse(dt.value),cmp_dd.value,selected_id(branch_dd),selected_id(cc_dd))))
            except Exception as ex_:
                cmp_block=ft.Text('تعذر حساب المقارنة: '+str(ex_),size=11,color=theme.TEXT_MUTED)
            cash_block=ft.Container()
            try:
                if parse(df.value) and parse(dt.value):
                    cash_block=theme.card(_cash_section(insights.cash_summary(parse(df.value),parse(dt.value),selected_id(branch_dd),selected_id(cc_dd))))
            except Exception as ex_:
                cash_block=ft.Text('تعذر حساب التدفق النقدي: '+str(ex_),size=11,color=theme.TEXT_MUTED)
            budget_rows=k['budget_vs_actual']
            budget_total=sum(x['budget'] for x in budget_rows); actual_total=sum(x['actual'] for x in budget_rows); variance=actual_total-budget_total
            budget_card=_card("Budget vs Actual",f"{_money(actual_total)} / {_money(budget_total)}",ft.Icons.SPEED,theme.PRIMARY,
                              lambda e:_open_details(page,"تحليل الموازنة مقابل الفعلي",[("account","الحساب"),("type","النوع"),("budget","الموازنة"),("actual","الفعلي"),("variance","الانحراف"),("achievement_pct","% التنفيذ")],
                              [{'account':x['code']+' - '+x['account'],'type':'إيراد' if x['type']=='income' else 'مصروف','budget':_money(x['budget']),'actual':_money(x['actual']),'variance':_money(x['variance']),'achievement_pct':_pct(x['achievement_pct'])} for x in budget_rows]),
                              f"الانحراف: {_money(variance)}")
            inv_cards=_grid([
                _card("قيمة المخزون",_money(inv['total_value']),ft.Icons.INVENTORY_2,theme.PRIMARY,lambda e:_open_details(page,"أعلى الأصناف قيمة",[("sku","الكود"),("name","الصنف"),("balance","الرصيد"),("unit","الوحدة"),("value","القيمة")],[{'sku':x['sku'],'name':x['name'],'balance':f"{x['balance']:g}",'unit':x['unit'],'value':_money(x['value'])} for x in inv['top']])),
                _card("الأصناف منخفضة المخزون",str(inv['low_count']),ft.Icons.WARNING_AMBER,theme.DANGER,lambda e:_open_details(page,"الأصناف التي تحتاج طلب",[("sku","الكود"),("name","الصنف"),("balance","الرصيد"),("reorder_point","حد الطلب")],[{'sku':x['sku'],'name':x['name'],'balance':f"{x['balance']:g}",'reorder_point':f"{x['reorder_point']:g}"} for x in inv['low']])),
            ],lg=6)
            branch_rows=data['branches']; bkey='profit' if show_profit else 'sales_total'
            if not show_profit: branch_rows=sorted(branch_rows,key=lambda x:float(x.get('sales_total',0) or 0),reverse=True)
            max_profit=max([abs(float(x.get(bkey,0) or 0)) for x in branch_rows] or [1]) or 1
            branch_visual=ft.Column([ft.Container(content=_bar_row(x['branch'],x[bkey],max_profit,_money(x[bkey]),theme.SUCCESS if (x[bkey] or 0)>=0 else theme.DANGER),on_click=lambda e,x=x:_open_details(page,f"تفاصيل فرع {x['branch']}",[("branch","الفرع"),("sales_total","المبيعات"),("expense","المصروفات")]+([("profit","الربح")] if show_profit else [])+[("assets","الأصول"),("liabilities","الالتزامات")],[{'branch':x['branch'],'sales_total':_money(x['sales_total']),'expense':_money(x['expense']),'profit':_money(x['profit']),'assets':_money(x['assets']),'liabilities':_money(x['liabilities'])}])) for x in branch_rows],spacing=5)
            cust=data['customers']; cmax=max([x['sales'] for x in cust] or [1]) or 1; prod=data['products']; pmax=max([x['sales'] for x in prod] or [1]) or 1
            cust_visual=ft.Column([ft.Container(content=_bar_row(x['name'],x['sales'],cmax,_money(x['sales']),theme.PRIMARY),on_click=lambda e,x=x:_open_details(page,f"تفاصيل العميل {x['name']}",[("number","الفاتورة"),("date","التاريخ"),("subtotal","قبل الضريبة"),("tax","الضريبة"),("total","الإجمالي")],[{'number':z['number'],'date':z['date'],'subtotal':_money(z['subtotal']),'tax':_money(z['tax']),'total':_money(z['total'])} for z in services.executive_customer_detail(x['id'],parse(df.value),parse(dt.value),selected_id(branch_dd),selected_id(cc_dd))])) for x in cust],spacing=5)
            prod_visual=ft.Column([ft.Container(content=_bar_row(x['name'],x['sales'],pmax,_money(x['sales']),theme.SECONDARY),on_click=lambda e,x=x:_open_details(page,f"تفاصيل الصنف {x['name']}",[("number","الفاتورة"),("date","التاريخ"),("customer","العميل"),("qty","الكمية"),("unit_price","السعر"),("total","الإجمالي")],[{'number':z['number'],'date':z['date'],'customer':z['customer'],'qty':f"{z['qty']:g}",'unit_price':_money(z['unit_price']),'total':_money(z['total'])} for z in services.executive_product_detail(x['id'],parse(df.value),parse(dt.value),selected_id(branch_dd),selected_id(cc_dd))])) for x in prod],spacing=5)
            aging_visual=ft.Column([ft.Container(content=_bar_row(bucket,amount,(max(aging['buckets'].values() or [1]) or 1),_money(amount),theme.WARNING),on_click=lambda e,b=bucket:_open_details(page,f"تفاصيل أعمار الذمم - {b}",[("party","العميل"),("number","الفاتورة"),("date","التاريخ"),("days","الأيام"),("due","المستحق")],[{'party':x['party'],'number':x['number'],'date':x['date'].strftime('%Y-%m-%d'),'days':x['days'],'due':_money(x['due'])} for x in aging['rows'] if x['bucket']==b])) for bucket,amount in aging['buckets'].items()],spacing=6)
            root.controls=[
                theme.page_title("لوحة الإدارة التنفيذية","مؤشرات الأداء والربحية والمبيعات والموازنة والعملاء والمخزون",ft.Icons.SPACE_DASHBOARD_OUTLINED),
                theme.card(ft.Row([branch_dd,cc_dd,rng.control,cmp_dd,ft.FilledButton("تحديث",icon=ft.Icons.REFRESH,bgcolor=theme.PRIMARY,on_click=refresh)],wrap=True,spacing=10,run_spacing=10),padding=14),
                *([_is] if (_is:=_integrity_strip(page)) else []),
                kpis,ratios,
                *extra,
                *([ob] if (ob:=onboarding_view.onboarding_card(page,refresh)) else []),
                cmp_block,cash_block,
                theme.card(ft.Column([_section("المبيعات والمصروفات والأرباح شهرياً","اضغط على أي شهر لعرض تفاصيله"),_monthly_chart(data['monthly'],lambda x:_open_details(page,f"تفاصيل شهر {x['label']}",[("item","المؤشر"),("value","القيمة"),("count","العدد")],[{'item':'المبيعات','value':_money(x['revenue']),'count':x['sales_count']},{'item':'المصروفات','value':_money(x['expense']),'count':x['purchase_count']},{'item':'صافي الربح','value':_money(x['profit']),'count':'-'}]))],spacing=12)),
                inv_cards,
                ft.Row([theme.card(ft.Column([_section("ترتيب الفروع حسب "+("الربح" if show_profit else "المبيعات"),"اضغط على أي فرع للتفاصيل"),branch_visual],spacing=10),expand=True),theme.card(ft.Column([_section("Budget vs Actual","اضغط على البطاقة لعرض الحسابات"),budget_card],spacing=10),expand=True)],spacing=12),
                ft.Row([theme.card(ft.Column([_section("أفضل العملاء","حسب قيمة المبيعات"),cust_visual],spacing=10),expand=True),theme.card(ft.Column([_section("أفضل الأصناف","حسب قيمة المبيعات"),prod_visual],spacing=10),expand=True)],spacing=12),
                theme.card(ft.Column([_section("أعمار الذمم المدينة","اضغط على أي شريحة لعرض الفواتير المستحقة"),aging_visual],spacing=10)),
                status,
            ]
            page.update()
        except Exception as ex:
            status.value=str(ex); page.update()
    branch_dd.on_change=refresh; cc_dd.on_change=refresh; cmp_dd.on_select=refresh
    refresh()
    return root
