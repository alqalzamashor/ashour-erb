import datetime
import flet as ft
from .. import fx, services, theme
from ..report_export import export_excel, export_pdf


def build_currencies(page: ft.Page):
    """العملات وأسعار الصرف + إعادة تقييم أرصدة العملاء والموردين بالأجنبي (فروق العملة)."""
    services.require_action('currencies', 'view')
    u = services._get_user()
    can_edit = services.user_has_action(u, 'currencies', 'edit')
    can_post = services.user_has_action(u, 'currencies', 'post')
    st = {'prev': []}
    cur_col = ft.Column(spacing=2)
    rates_col = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, height=240)
    reval_col = ft.Column(spacing=2)
    msg = ft.Text('', size=12)

    def say(m, ok=True):
        msg.value = m; msg.color = theme.SUCCESS if ok else theme.DANGER; page.update()

    cur_dd = ft.Dropdown(label='العملة', width=130)
    rate_date = ft.TextField(label='التاريخ', width=140, value=datetime.date.today().isoformat())
    rate_f = ft.TextField(label='السعر (ريال لكل 1)', width=160, keyboard_type=ft.KeyboardType.NUMBER)
    code_f = ft.TextField(label='رمز العملة (USD)', width=140)
    name_f = ft.TextField(label='الاسم', width=180)
    sym_f = ft.TextField(label='الرمز', width=100)
    reval_date = ft.TextField(label='إعادة التقييم بتاريخ', width=170, value=datetime.date.today().isoformat())

    def load(e=None):
        curs = fx.list_currencies()
        foreign = [c for c in curs if not c.is_base]
        cur_col.controls = [ft.Text(f"{c.code}  {c.name}  {c.symbol}" + ('  (الأساسية)' if c.is_base else ''), size=13) for c in curs]
        cur_dd.options = [ft.dropdown.Option(c.code, c.code) for c in foreign]
        if not cur_dd.value and foreign:
            cur_dd.value = foreign[0].code
        rates_col.controls = [ft.Text(f"{r.currency_code}   {r.rate_date:%Y-%m-%d}   {r.rate:g}", size=12) for r in fx.list_rates()] or [ft.Text('مفيش أسعار', color=theme.TEXT_MUTED)]
        if e is not None:
            page.update()

    def add_cur(e):
        try:
            fx.add_currency(code_f.value, name_f.value, sym_f.value); code_f.value = name_f.value = sym_f.value = ''; load(); say('اتضافت'); 
        except Exception as ex:
            say(str(ex), False)

    def add_rate(e):
        try:
            fx.set_rate(cur_dd.value, datetime.date.fromisoformat(rate_date.value.strip()), rate_f.value); rate_f.value = ''; load(); say('اتسجّل السعر')
        except Exception as ex:
            say(str(ex), False)

    def do_preview(e=None):
        try:
            d = datetime.date.fromisoformat(reval_date.value.strip())
            st['prev'] = fx.preview(d)
        except Exception as ex:
            say(str(ex), False); return
        reval_col.controls = [ft.Row([ft.Text(x, size=12, weight=ft.FontWeight.BOLD, expand=1) for x in ('الطرف', 'العملة', 'الرصيد الأجنبي', 'السعر', 'الدفتري', 'بعد التقييم', 'الفرق')])] + [
            ft.Row([ft.Text('عميل ' if r['party_type'] == 'customer' else 'مورد ', size=12) if False else ft.Text(('ع: ' if r['party_type'] == 'customer' else 'م: ') + r['party'], size=12, expand=1),
                    ft.Text(r['currency'], size=12, expand=1), ft.Text(f"{r['foreign_balance']:,.2f}", size=12, expand=1), ft.Text(f"{r['rate']:g}", size=12, expand=1),
                    ft.Text(f"{r['book_before']:,.2f}", size=12, expand=1), ft.Text(f"{r['target']:,.2f}", size=12, expand=1),
                    ft.Text(f"{r['adjustment']:+,.2f}", size=12, expand=1, color=theme.SUCCESS if (r['adjustment'] > 0) == (r['party_type'] == 'customer') else theme.DANGER)]) for r in st['prev']] \
            or [ft.Text('مفيش فروق عملة تحتاج ترحيل', color=theme.TEXT_MUTED)]
        page.update()

    def do_post(e):
        try:
            r = fx.post_revaluation(datetime.date.fromisoformat(reval_date.value.strip()))
            do_preview(); say(f"اترحّل قيد فروق عملة لـ {r['count']} طرف (أرباح {r['gain']:,.2f} / خسائر {r['loss']:,.2f})" if r['count'] else 'مفيش فروق')
        except Exception as ex:
            say(str(ex), False)

    load()
    return ft.Column([
        theme.page_title('العملات وأسعار الصرف', 'سجّل العملات والأسعار، واعمل فواتير وسندات بالأجنبي، وبعدين «إعادة التقييم» بتحسب فروق العملة بقيد محاسبي'),
        theme.card(ft.Column([ft.Text('العملات', weight=ft.FontWeight.BOLD), cur_col, ft.Row([code_f, name_f, sym_f, ft.OutlinedButton('إضافة عملة', on_click=add_cur, disabled=not can_edit)], wrap=True)], spacing=8), padding=14),
        theme.card(ft.Column([ft.Text('أسعار الصرف', weight=ft.FontWeight.BOLD), ft.Row([cur_dd, rate_date, rate_f, ft.OutlinedButton('تسجيل السعر', on_click=add_rate, disabled=not can_edit)], wrap=True), rates_col], spacing=8), padding=14),
        theme.card(ft.Column([ft.Text('إعادة تقييم العملات', weight=ft.FontWeight.BOLD),
                              ft.Text('رصيد كل عميل/مورد بالأجنبي × سعر التاريخ − رصيده الدفتري بالريال = فرق عملة (محقق لو الرصيد الأجنبي صفر، غير محقق لو لسه فيه رصيد). بيتعمل قيد واحد، وتشغيله تاني بنفس السعر مش بيكرر.', size=12, color=theme.TEXT_MUTED),
                              ft.Row([reval_date, ft.OutlinedButton('معاينة', on_click=do_preview), ft.FilledButton('ترحيل القيد', bgcolor=theme.PRIMARY, on_click=do_post, disabled=not can_post)], wrap=True), reval_col], spacing=8), padding=14),
        msg,
    ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=12)
