import asyncio
import flet as ft
import datetime
from . import i18n as _i18n

# Flet 0.86: ft.Dropdown ليس له on_change (الحدث اسمه on_select)، وتعيين on_change كان بيتجاهل بصمت في عشرات الشاشات.
# الـshim ده بيحوّل on_change لـon_select عشان كل الشاشات القديمة تشتغل من غير تعديل واحدة واحدة.
if not isinstance(getattr(ft.Dropdown, 'on_change', None), property):
    ft.Dropdown.on_change = property(lambda self: self.on_select, lambda self, v: setattr(self, 'on_select', v))

PRIMARY = "#1A7A5E"
PRIMARY_DARK = "#0F5A45"
PRIMARY_LIGHT = "#EAF5F0"     # خلفية فاتحة لتمييز عناصر مرتبطة بالحساب الرئيسي
SECONDARY = "#F2B84B"
DANGER = "#E5484D"
DANGER_LIGHT = "#FDECEA"
WARNING = "#F5A524"
WARNING_LIGHT = "#FEF3DD"
SUCCESS = "#17C964"
SUCCESS_LIGHT = "#E7F9EF"
BG = "#F5F8F6"
SIDEBAR_BG = "#0F2F27"
SIDEBAR_BG_2 = "#143D33"      # نهاية تدرّج الشريط الجانبي
CARD_BG = "#FFFFFF"
TEXT_MUTED = "#7A8A84"
MAIN_ROW_BG = "#EAF5F0"          # خلفية صفوف الحسابات الرئيسية في الجداول
BORDER_LIGHT = "#E3EBE7"      # فواصل وحدود هادئة موحّدة لكل الشاشات

PRIMARY_TEXT = PRIMARY_DARK      # لون نص بلون الهوية (بيفتح في الوضع الليلي عشان يبان على الخلفية الغامقة)
TEXT = "#14281F"                 # لون النص الأساسي / العناوين
SURFACE_ALT = "#EDF3F0"          # خلفية ثانوية (أزرار غير نشطة، شرائط تقدّم...)
SUCCESS_TEXT = "#0E7A3F"          # نص أخضر غامق (بيفتح في الوضع الليلي)
WARNING_TEXT = "#8A5A00"         # نص التنبيهات (أصفر غامق)
ROW_BG = ("#FFFFFF", "#F6FAF8")   # تبديل ألوان صفوف الشبكات

# ---- الوضع الليلي ----
# كل الشاشات بتقرا الألوان من هنا وقت البناء (theme.X)، فتبديل القيم ثم إعادة بناء الشاشة الحالية بيكفي.
_LIGHT = dict(BG=BG, CARD_BG=CARD_BG, PRIMARY_LIGHT=PRIMARY_LIGHT, MAIN_ROW_BG=MAIN_ROW_BG, BORDER_LIGHT=BORDER_LIGHT, TEXT_MUTED=TEXT_MUTED,
              SUCCESS_LIGHT=SUCCESS_LIGHT, DANGER_LIGHT=DANGER_LIGHT, WARNING_LIGHT=WARNING_LIGHT, PRIMARY_TEXT=PRIMARY_TEXT,
              TEXT=TEXT, SURFACE_ALT=SURFACE_ALT, WARNING_TEXT=WARNING_TEXT, ROW_BG=ROW_BG, PRIMARY=PRIMARY, SUCCESS_TEXT=SUCCESS_TEXT)
_DARK = dict(BG="#0E1A16", CARD_BG="#16251F", PRIMARY_LIGHT="#1B3A30", MAIN_ROW_BG="#1B3A30", BORDER_LIGHT="#2A413A", TEXT_MUTED="#9DB1A9",
             SUCCESS_LIGHT="#14382A", DANGER_LIGHT="#43202A", WARNING_LIGHT="#443619", PRIMARY_TEXT="#7BD9B4",
             TEXT="#E8F1ED", SURFACE_ALT="#1F332C", WARNING_TEXT="#F5C46B", ROW_BG=("#16251F", "#1B2D26"),
             PRIMARY="#2FA07E", SUCCESS_TEXT="#5FD79A")      # أخضر أفتح في الليلي: نصوص وأيقونات بلون الهوية بتبان على الخلفية الغامقة (الأزرار لسه نصها أبيض)
DARK = False
_PREF_PATH = None


def _pref_path():
    global _PREF_PATH
    if _PREF_PATH is None:
        import os
        try:
            from .db import APP_DIR
            _PREF_PATH = os.path.join(APP_DIR, "ui_prefs.json")
        except Exception:
            _PREF_PATH = "ui_prefs.json"
    return _PREF_PATH


def set_dark(on, save=True):
    """بدّل لوحة الألوان (فاتح/ليلي). بعدها لازم تعيد بناء الشاشة الحالية عشان الألوان الجديدة تتطبّق."""
    global DARK
    DARK = bool(on)
    globals().update(_DARK if DARK else _LIGHT)
    if save:
        import json
        try:
            with open(_pref_path(), "w", encoding="utf-8") as f:
                json.dump({"dark": DARK}, f)
        except Exception:
            pass
    return DARK


def load_mode():
    import json
    try:
        with open(_pref_path(), encoding="utf-8") as f:
            return set_dark(bool(json.load(f).get("dark")), save=False)
    except Exception:
        return set_dark(False, save=False)


FONT_FAMILY = "Cairo"
RADIUS = 14                   # نصف قطر الحواف الموحّد (بطاقات/أزرار/حوارات)


def app_theme(dark=False):
    """الثيم العام: خط الهوية + أزرار بحواف موحّدة وبدون ظل ثقيل + جداول بترويسة هادئة + حوارات مدوّرة.
    كل شاشة بتاخد الشكل ده تلقائيًا من غير تعديل كل زرار لوحده (آمن: فيه fallback لثيم الحد الأدنى)."""
    try:
        shape = lambda r=10: ft.RoundedRectangleBorder(radius=r)
        btn_pad = ft.Padding.symmetric(horizontal=18, vertical=12)
        return ft.Theme(
            font_family=FONT_FAMILY, color_scheme_seed=PRIMARY,
            filled_button_theme=ft.FilledButtonTheme(style=ft.ButtonStyle(shape=shape(), padding=btn_pad, elevation=0, **({'color': '#FFFFFF'} if dark else {}), text_style=ft.TextStyle(font_family=FONT_FAMILY, size=13.5, weight=ft.FontWeight.W_700))),
            outlined_button_theme=ft.OutlinedButtonTheme(style=ft.ButtonStyle(shape=shape(), padding=btn_pad, text_style=ft.TextStyle(font_family=FONT_FAMILY, size=13.5, weight=ft.FontWeight.W_600))),
            text_button_theme=ft.TextButtonTheme(style=ft.ButtonStyle(shape=shape(8), text_style=ft.TextStyle(font_family=FONT_FAMILY, size=13.5, weight=ft.FontWeight.W_600))),
            dialog_theme=ft.DialogTheme(shape=shape(16)),
            data_table_theme=ft.DataTableTheme(
                heading_row_color=SURFACE_ALT, heading_text_style=ft.TextStyle(font_family=FONT_FAMILY, size=12.5, weight=ft.FontWeight.W_800, color=TEXT),
                data_text_style=ft.TextStyle(font_family=FONT_FAMILY, size=13, color=TEXT), divider_thickness=0.6, horizontal_margin=14, column_spacing=22),
            divider_theme=ft.DividerTheme(color=BORDER_LIGHT, thickness=1),
            tooltip_theme=ft.TooltipTheme(text_style=ft.TextStyle(font_family=FONT_FAMILY, size=12, color="#FFFFFF"), decoration=ft.BoxDecoration(bgcolor="#2A2542", border_radius=8)),
        )
    except Exception:
        return ft.Theme(font_family=FONT_FAMILY, color_scheme_seed=PRIMARY)

def stat_card(label, value, color=None, sub="", size=22, padding=14, width=230):
    """كارت إحصائية موحّد لأعلى الشاشات: شريط لوني جانبي + عنوان صغير + رقم كبير بلون الحالة + سطر وصف. value نص جاهز (التنسيق على المستدعي)."""
    color = color or PRIMARY
    shown = TEXT if color in (None, TEXT_MUTED) else color
    body = ft.Column([ft.Text(label, size=12, color=TEXT_MUTED),
                      ft.Text(str(value), size=size, weight=ft.FontWeight.W_800, color=shown)]
                     + ([ft.Text(sub, size=11, color=TEXT_MUTED)] if sub else []), spacing=1, tight=True)
    strip = ft.Container(width=4, height=58 if sub else 46, bgcolor=color, border_radius=3)
    mw = _page_w()
    if mw:                       # موبايل: كارتين جنب بعض بدل ما يتكدّسوا
        width = max(140, (mw - 32 - 10) / 2)
        body.controls[1].size = min(size, 20)
        body.width = max(60, width - 20 - 4 - 10)     # عرض ثابت للنص: العناوين الطويلة تنزل سطر تاني بدل ما تخرج بره الكارت
    c = card(ft.Row([strip, body], spacing=10 if mw else 12, vertical_alignment=ft.CrossAxisAlignment.START, tight=True), padding=10 if mw else padding)
    c.width = width
    c.__dict__['_erp_stat'] = True
    return c


def status_badge(text, color=None, size=11.5):
    """شارة حالة: كبسولة بخلفية خفيفة من لون الحالة ونص بنفس اللون (مسدد/ملغى/معلّق...). بتشتغل في الفاتح والليلي، والنص جواها بيتقرا للفرز والطباعة زي أي خلية."""
    color = color or TEXT_MUTED
    fg = WARNING_TEXT if color == WARNING else color
    pill = ft.Container(content=ft.Text(str(text), size=size, weight=ft.FontWeight.W_700, color=fg, no_wrap=True),
                        bgcolor=ft.Colors.with_opacity(0.14, color), border_radius=20,
                        padding=ft.Padding(left=10, right=10, top=3, bottom=3))
    return ft.Row([pill], tight=True, spacing=0)          # جوه Row: مبيتمدّدش على عرض الكارت لما العمود بيعمل stretch (موبايل)


def ref_dropdown(items, label, text_fn, value=None, width=280, hint_text=None):
    """قايمة بحث جاهزة لاختيار سجل من جدول مرجعي (عملاء/موردين/حسابات/
    أصناف/موظفين...) - بتبني خيارات SearchableDropdown من قايمة كائنات
    مباشرة (ID = str(item.id))، عشان نقلل تكرار نفس الكود في كل شاشة.
    items: قايمة كائنات (لكل واحد .id). text_fn(item) -> النص المعروض."""
    options = [(str(getattr(it, 'id')), text_fn(it)) for it in items]
    return SearchableDropdown(label=label, width=width, options=options,
                              value=str(value) if value is not None else None, hint_text=hint_text)


def card(content, padding=20, expand=None):
    """البطاقة الموحّدة لكل الشاشات: حواف مدوّرة، ظل ناعم مزدوج الطبقة
    (طبقة قريبة دقيقة + طبقة بعيدة ناعمة) بدل ظل واحد مسطّح، وحد رفيع
    شبه شفاف بيدي إحساس عمق خفيف من غير ما يبان تقيل."""
    return ft.Container(
        content=content,
        bgcolor=CARD_BG,
        border_radius=RADIUS,
        padding=padding,
        expand=expand,
        border=ft.border.Border(*(ft.border.BorderSide(1, BORDER_LIGHT) for _ in range(4))),
        shadow=ft.BoxShadow(
            spread_radius=0, blur_radius=18,
            color=ft.Colors.with_opacity(0.07, "#0F2F27"),
            offset=ft.Offset(0, 4),
        ),
    )


def page_title(text, subtitle=None, icon=None):
    """عنوان الشاشة الموحّد: شريط لوني رفيع + عنوان بخط واضح + وصف مختصر
    تحته - نفس التركيبة بتتكرر أعلى كل شاشة في البرنامج فبتدّي هوية بصرية
    موحّدة. icon اختياري (أيقونة الشاشة نفسها من main.py) لسياق بصري إضافي."""
    accent = ft.Container(width=4, height=30, bgcolor=PRIMARY, border_radius=3)
    title_row = [ft.Text(text, size=23, weight=ft.FontWeight.W_800, color=TEXT)]
    if icon:
        title_row.insert(0, ft.Icon(icon, size=22, color=PRIMARY))
    col = [ft.Row(title_row, spacing=8)]
    if subtitle:
        col.append(ft.Text(subtitle, size=13, color=TEXT_MUTED))
    cw = _page_w()
    # موبايل: عنوان ووصف طويلين بيلفّوا بدل ما يتقصّوا
    return ft.Row([accent, ft.Column(col, spacing=3, width=(max(120, cw - 60) if cw else None))], spacing=12)


def section_title(text, icon=None):
    """عنوان قسم فرعي داخل بطاقة (نفس النمط اللي بيتكرر يدويًا في عشرات
    الشاشات: ft.Text(..., size=16, weight=BOLD)) - موحّد هنا بدل ما يتكرر."""
    controls = []
    if icon:
        controls.append(ft.Icon(icon, size=18, color=PRIMARY))
    controls.append(ft.Text(text, size=16, weight=ft.FontWeight.W_700, color=TEXT))
    return ft.Row(controls, spacing=8)


class MultiCheckList:
    """بديل لـ ft.Dropdown(multiselect=True) اللي اتشالت من Flet الحديثة.
    نفس واجهة الاستخدام تقريباً:
        ml = theme.MultiCheckList('الفروع', page)
        ml.add_option('1', 'الفرع الرئيسي')
        ...
        ml.value              # -> ['1', '3']  (قراءة المحدد)
        ml.value = ['1']      # (لتحديد قيم مبدئياً أو التصفير بـ [])
        some_row.controls.append(ml.control)
    """

    def __init__(self, label, page=None, width=280, max_height=140):
        self.page = page
        self._checks = []  # [(key, ft.Checkbox), ...]
        self._column = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, height=max_height)
        _side = ft.border.BorderSide(width=1, color=BORDER_LIGHT)
        self.control = ft.Container(
            content=ft.Column(
                [ft.Text(label, size=12, color=TEXT_MUTED), self._column],
                spacing=4, tight=True,
            ),
            border=ft.border.Border(top=_side, right=_side, bottom=_side, left=_side),
            border_radius=8, padding=10, width=width,
        )

    def add_option(self, key, text):
        cb = ft.Checkbox(label=text, value=False)
        self._checks.append((str(key), cb))
        self._column.controls.append(cb)

    @property
    def value(self):
        return [key for key, cb in self._checks if cb.value]

    @value.setter
    def value(self, keys):
        keys = set(str(k) for k in (keys or []))
        for key, cb in self._checks:
            cb.value = key in keys
        if self.page:
            self.page.update()


# ----------------------------------------------------------------------
# حقول التاريخ: لوحة منسدلة بنفس شكل Odoo (اختصارات جاهزة + من/إلى + تطبيق) بألوان البرنامج
# ----------------------------------------------------------------------
_DATE_FORMATS = ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%Y/%m/%d', '%d.%m.%Y')


def parse_date_text(text):
    """بيقبل 01/10/2026 أو 2026-10-01 أو 1-10-2026 ... ويرجّع datetime.date أو None."""
    t = (str(text or '')).strip()
    if not t:
        return None
    for f in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(t, f).date()
        except ValueError:
            continue
    return None


def format_date_display(d):
    return d.strftime('%d/%m/%Y') if d else ''


def _month_bounds(d):
    import calendar
    return d.replace(day=1), d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _add_months_date(d, n):
    import calendar
    m = d.month - 1 + n
    y = d.year + m // 12; m = m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def _quarter_bounds(d, offset=0):
    q0 = d.replace(day=1, month=((d.month - 1) // 3) * 3 + 1)
    start = _add_months_date(q0, 3 * offset)
    return start, _month_bounds(_add_months_date(start, 2))[1]


def _fiscal_year_bounds(d, offset=0):
    """السنة المالية الحالية/السابقة: من جدول الفترات المحاسبية السنوية لو موجود، وإلا السنة الميلادية."""
    try:
        from . import services
        years = [p for p in services.list_fiscal_periods() if (p.date_to.date() - p.date_from.date()).days >= 300]
        cur = next((p for p in years if p.date_from.date() <= d <= p.date_to.date()), None)
        if cur:
            if offset == 0:
                return cur.date_from.date(), cur.date_to.date()
            prev_day = cur.date_from.date() - datetime.timedelta(days=1)
            prev = next((p for p in years if p.date_from.date() <= prev_day <= p.date_to.date()), None)
            if prev:
                return prev.date_from.date(), prev.date_to.date()
            return _add_months_date(cur.date_from.date(), -12), prev_day
    except Exception:
        pass
    y = d.year + offset
    return datetime.date(y, 1, 1), datetime.date(y, 12, 31)


def range_presets(today=None):
    """اختصارات الفترات (زي Odoo): (مفتاح، نص، من، إلى)."""
    t = today or datetime.date.today()
    last_month = _month_bounds(_add_months_date(t.replace(day=1), -1))
    return [
        ('this_month', 'هذا الشهر', *_month_bounds(t)), ('this_quarter', 'هذا الربع', *_quarter_bounds(t, 0)), ('this_fy', 'هذه السنة المالية', *_fiscal_year_bounds(t, 0)),
        ('last_month', 'الشهر الماضي', *last_month), ('last_quarter', 'الربع الماضي', *_quarter_bounds(t, -1)), ('last_fy', 'السنة المالية الماضية', *_fiscal_year_bounds(t, -1)),
    ]


def single_presets(today=None):
    t = today or datetime.date.today()
    ms, me = _month_bounds(t)
    return [('today', 'اليوم', t), ('yesterday', 'أمس', t - datetime.timedelta(days=1)), ('tomorrow', 'غدًا', t + datetime.timedelta(days=1)),
            ('month_start', 'بداية هذا الشهر', ms), ('month_end', 'نهاية هذا الشهر', me), ('year_start', 'بداية هذه السنة', t.replace(month=1, day=1)), ('year_end', 'نهاية هذه السنة', t.replace(month=12, day=31))]


def _make_date_picker(on_change, value=None):
    """تقويم Flet الأصلي بنصوص عربية وأسماء شهور عربي (locale ar)."""
    return ft.DatePicker(value=value, first_date=datetime.date(2015, 1, 1), last_date=datetime.date(2035, 12, 31), on_change=on_change,
                         locale=ft.Locale('ar'), help_text='اختر التاريخ', cancel_text='إلغاء', confirm_text='تطبيق', field_label_text='التاريخ (يوم/شهر/سنة)',
                         error_format_text='صيغة التاريخ غير صحيحة', error_invalid_text='التاريخ خارج النطاق')


class _MenuBase:
    """قايمة منسدلة صغيرة بتنزل تحت الحقل مباشرة (PopupMenuButton بتتثبّت تحت الزرار الشفاف اللي فوق الحقل):
    اختصارات جاهزة + خط فاصل، وتعليمة ✓ على الاختيار الحالي. بنفس شكل Odoo وبألوان البرنامج."""

    ITEM_HEIGHT = 34

    def _item(self, text, on_click, selected=False, icon=None, color=None):
        lead = (ft.Icon(ft.Icons.CHECK, size=15, color=PRIMARY) if selected else (ft.Icon(icon, size=15, color=color or TEXT_MUTED) if icon else ft.Container(width=15)))
        return ft.PopupMenuItem(
            height=self.ITEM_HEIGHT, padding=ft.Padding(left=12, right=12, top=0, bottom=0), on_click=on_click,
            content=ft.Container(width=getattr(self, 'ITEM_WIDTH', None), bgcolor=PRIMARY_LIGHT if selected else None, border_radius=6, padding=ft.Padding(left=6, right=8, top=5, bottom=5),
                                 content=ft.Row([lead, ft.Text(text, size=13, weight=ft.FontWeight.BOLD if selected else None, color=color or (PRIMARY_TEXT if selected else None))], spacing=8, tight=True)))

    @staticmethod
    def _sep():
        return ft.PopupMenuItem(height=7, padding=ft.Padding(left=10, right=10, top=0, bottom=0), content=ft.Divider(height=1, thickness=1, color=BORDER_LIGHT))

    def _build_anchor(self, width, min_menu_width):
        """الحقل (TextField للقراءة بس) + زرار شفاف فوقه بنفس الحجم بيفتح القايمة تحته بالظبط."""
        self.ITEM_WIDTH = min_menu_width - 24          # عرض صف العنصر المعلَّم = عرض القايمة ناقص الهوامش (تظليل الصف كله زي Odoo)
        self.popup = ft.PopupMenuButton(
            padding=0, menu_position=ft.PopupMenuPosition.UNDER, bgcolor=CARD_BG, elevation=6, shape=ft.RoundedRectangleBorder(radius=12),
            menu_padding=ft.Padding(left=0, right=0, top=5, bottom=5), size_constraints=ft.BoxConstraints(min_width=min_menu_width, max_width=min_menu_width),
            content=ft.Container(width=width, height=56, bgcolor=ft.Colors.TRANSPARENT), items=[])
        self.control = ft.Stack([self.text_field, self.popup], width=width, height=56)

    def _update(self):
        try:
            if self.page:
                self.page.update()
        except Exception:
            pass


class DateField(_MenuBase):
    """حقل تاريخ: ضغطة عليه بتنزّل قايمة صغيرة تحته مباشرة فيها اختصارات (اليوم / أمس / غدًا / بداية ونهاية الشهر / بداية السنة)
    و"اختيار من التقويم" (والتقويم نفسه فيه خيار الكتابة اليدوية). بيعرض التاريخ بصيغة يوم/شهر/سنة.
    الواجهة زي ما كانت: .value نص 'YYYY-MM-DD' و.on_change و.control.

        d = theme.DateField('تاريخ الفاتورة', page, width=150, value='2026-01-01')
        d.on_change = refresh;  row.controls.append(d.control);  d.value  # '2026-01-01'
    """

    def __init__(self, label='', page=None, width=160, value=None):
        self.page = page
        self.on_change = None
        self._picker_added = False
        self.label = label
        d = parse_date_text(value)
        self.text_field = ft.TextField(label=label, width=width, value=format_date_display(d), read_only=True, suffix_icon=ft.Icons.CALENDAR_MONTH, hint_text='يوم/شهر/سنة')
        self.picker = _make_date_picker(self._on_picked, datetime.datetime.combine(d, datetime.time()) if d else None)
        self._build_anchor(width, max(width, 180))
        self._refresh_menu()
        if page is not None:
            self.attach(page)

    @staticmethod
    def _parse(value):
        d = parse_date_text(value)
        return datetime.datetime.combine(d, datetime.time()) if d else None

    def attach(self, page):
        self.page = page
        if not self._picker_added:
            page.overlay.append(self.picker)
            self._picker_added = True

    # ---- القيمة
    @property
    def value(self):
        d = parse_date_text(self.text_field.value)
        return d.strftime('%Y-%m-%d') if d else ''

    @value.setter
    def value(self, v):
        d = parse_date_text(v)
        self.text_field.value = format_date_display(d)
        if d:
            self.picker.value = datetime.datetime.combine(d, datetime.time())
        self._refresh_menu()

    def _refresh_menu(self):
        cur = parse_date_text(self.text_field.value)
        items = [self._item(txt, lambda ev, dd=dd: self._apply(dd), selected=(cur == dd)) for k, txt, dd in single_presets() if k in ('today', 'yesterday', 'tomorrow')]
        items.append(self._sep())
        items += [self._item(txt, lambda ev, dd=dd: self._apply(dd), selected=(cur == dd)) for k, txt, dd in single_presets() if k in ('month_start', 'month_end', 'year_start')]
        items += [self._sep(), self._item('اختيار من التقويم...', self._open_calendar, icon=ft.Icons.CALENDAR_MONTH, color=PRIMARY)]
        if cur:
            items.append(self._item('مسح التاريخ', lambda ev: self._apply(None), icon=ft.Icons.CLOSE, color=DANGER))
        self.popup.items = items

    def _apply(self, d, notify=True):
        self.text_field.value = format_date_display(d)
        if d:
            self.picker.value = datetime.datetime.combine(d, datetime.time())
        self._refresh_menu()
        self._update()
        if notify and self.on_change:
            self.on_change(type('DateChangeEvent', (), {'control': self})())

    def _open_calendar(self, e=None):
        if not self.page:
            return
        if not self._picker_added:
            self.attach(self.page)
        self.picker.open = True
        self._update()

    def _on_picked(self, e):
        if self.picker.value:
            d = self.picker.value
            # التقويم بيرجّع التاريخ بمنتصف الليل UTC؛ إضافة 12 ساعة بتتفادى ظهور "اليوم اللي قبله" في المناطق الزمنية الموجبة (زي +3)
            if hasattr(d, 'hour'):
                d = d + datetime.timedelta(hours=12)
            self._apply(d.date() if hasattr(d, 'date') else d)


class _RangeEnd:
    """طرف من نطاق التاريخ (من أو إلى) بنفس واجهة DateField (.value و.on_change) عشان باقي الكود ما يتغيّرش."""

    def __init__(self, owner, which):
        self._owner = owner
        self._which = which
        self.control = None

    @property
    def value(self):
        d = self._owner._start if self._which == 'start' else self._owner._end
        return d.strftime('%Y-%m-%d') if d else ''

    @value.setter
    def value(self, v):
        self._owner._set(self._which, parse_date_text(v))

    @property
    def on_change(self):
        return self._owner.on_change

    @on_change.setter
    def on_change(self, fn):
        self._owner._add_callback(fn)


class DateRangeField(_MenuBase):
    """حقل فترة (من - إلى): ضغطة عليه بتنزّل تحته مباشرة قايمة صغيرة بنفس شكل Odoo: (هذا الشهر / هذا الربع / هذه السنة المالية)
    (الشهر الماضي / الربع الماضي / السنة المالية الماضية) (كل الفترات) و"من ..." و"إلى ..." بتفتح التقويم. فاضي = كل الفترات.

        rng = theme.DateRangeField('الفترة', page, width=270)
        df, dt = rng.start, rng.end        # .value نص 'YYYY-MM-DD' زي DateField
        df.on_change = refresh             # أو rng.on_change = refresh (بيتنادى مرة واحدة)
        row.controls.append(rng.control)
    """

    def __init__(self, label='الفترة', page=None, width=290, start='', end='', allow_clear=True):
        self.page = page
        self.label = label
        self.allow_clear = allow_clear
        self._start = parse_date_text(start)
        self._end = parse_date_text(end)
        self._callbacks = []
        self._picker_for = None
        self.start = _RangeEnd(self, 'start')
        self.end = _RangeEnd(self, 'end')
        self.text_field = ft.TextField(label=label, width=width, value=self._display(), read_only=True, suffix_icon=ft.Icons.DATE_RANGE, hint_text='كل الفترات')
        self.picker = _make_date_picker(self._on_picked)
        self._picker_added = False
        self._build_anchor(width, max(width, 280))
        self._refresh_menu()
        if page is not None:
            self.attach(page)

    def attach(self, page):
        self.page = page
        if not self._picker_added:
            page.overlay.append(self.picker)
            self._picker_added = True

    @property
    def on_change(self):
        return self._callbacks[0] if self._callbacks else None

    @on_change.setter
    def on_change(self, fn):
        self._add_callback(fn)

    def _add_callback(self, fn):
        if fn is not None and not any(fn is c for c in self._callbacks):
            self._callbacks.append(fn)

    def _display(self):
        if not self._start and not self._end:
            return ''
        return f"{format_date_display(self._start) or '...'}  -  {format_date_display(self._end) or '...'}"

    def _set(self, which, d):
        if which == 'start':
            self._start = d
        else:
            self._end = d
        self.text_field.value = self._display()
        self._refresh_menu()

    def set_range(self, start, end):
        self._start, self._end = start, end
        self.text_field.value = self._display()
        self._refresh_menu()

    def _refresh_menu(self):
        presets = range_presets()
        cur = (self._start, self._end)
        sel = next((k for k, _t, a, b in presets if (a, b) == cur), None)
        mk = lambda k, txt, a, b: self._item(txt, lambda ev, a=a, b=b: self._apply(a, b), selected=(sel == k))
        items = [mk(*p) for p in presets[:3]] + [self._sep()] + [mk(*p) for p in presets[3:]]
        if self.allow_clear:
            items += [self._sep(), self._item('كل الفترات (بدون فلتر تاريخ)', lambda ev: self._apply(None, None), selected=(cur == (None, None)))]
        items += [self._sep(),
                  self._item(f"من:  {format_date_display(self._start) or 'اختر التاريخ'}", lambda ev: self._open_calendar('start'), icon=ft.Icons.CALENDAR_MONTH, color=PRIMARY),
                  self._item(f"إلى:  {format_date_display(self._end) or 'اختر التاريخ'}", lambda ev: self._open_calendar('end'), icon=ft.Icons.CALENDAR_MONTH, color=PRIMARY)]
        self.popup.items = items

    def _apply(self, start, end, notify=True):
        self.set_range(start, end)
        self._update()
        if notify:
            self._notify()

    def _notify(self):
        ev = type('DateRangeEvent', (), {'control': self})()
        for cb in list(self._callbacks):
            cb(ev)

    def _open_calendar(self, which):
        if not self.page:
            return
        self._picker_for = which
        cur = self._start if which == 'start' else self._end
        self.picker.value = datetime.datetime.combine(cur or datetime.date.today(), datetime.time())
        if not self._picker_added:
            self.attach(self.page)
        self.picker.open = True
        self._update()

    def _on_picked(self, e):
        which = self._picker_for
        if not which or not self.picker.value:
            return
        d = self.picker.value
        if hasattr(d, 'hour'):
            d = d + datetime.timedelta(hours=12)
        d = d.date() if hasattr(d, 'date') else d
        self._picker_for = None
        if which == 'start':
            s, en = d, self._end
            if en and en < d:
                en = d                      # "من" بعد "إلى" الحالي: بنخلّي "إلى" = نفس اليوم بدل ما نرفض
        else:
            s, en = self._start, d
            if s and s > d:
                s = d
        self._apply(s, en)


def call_without_page_update(page, fn, *args, **kwargs):
    """ينفّذ fn() (زي refresh() الأولى وقت بناء الشاشة) مع تعطيل أي نداء
    لـ page.update() جواها مؤقتاً. الشاشة لسه مش متلحّمة فعلياً بالصفحة
    في اللحظة دي، ونداء page.update() المبكر ده كان بيسبب ظهور مربع فاضي/
    رمادي بدل المحتوى في المتصفح الحقيقي. بعد ما الدالة تخلص، page.update
    بيرجع لطبيعته عادي لأي تفاعل لاحق من المستخدم."""
    original_update = page.update
    page.update = lambda *a, **k: None
    try:
        return fn(*args, **kwargs)
    finally:
        page.update = original_update


class SimpleTabs:
    """بديل بسيط وموثوق لـ ft.Tabs (اللي بقت واجهتها معقدة في نسخ Flet
    الحديثة وبتحتاج content/length مسبقاً). الاستخدام:

        tabs = theme.SimpleTabs()
        ...
        tabs.set_tabs([('ملخص', summary_control), ('التفاصيل', details_control)])
        ...
        some_layout = ft.Column([..., tabs.control, ...])

    ولإعادة بناء نفس التبويبات بعد تحديث البيانات، نادِ set_tabs() تاني
    بنفس عدد/ترتيب العناصر - التبويب المختار حالياً هيفضل زي ما هو.
    """

    def __init__(self, page=None):
        self.page = page
        self._tab_defs = []          # [(label, content_control), ...]
        self._selected_index = 0
        self._bar = ft.Row(spacing=4)
        self._body = ft.Container(expand=True)
        self.control = ft.Column([self._bar, ft.Container(height=8), self._body], expand=True)

    @property
    def selected_index(self):
        return self._selected_index

    def set_tabs(self, tab_defs, selected_index=None):
        self._tab_defs = list(tab_defs)
        if selected_index is not None:
            self._selected_index = selected_index
        self._selected_index = max(0, min(self._selected_index, len(self._tab_defs) - 1))
        self._render()

    def select(self, index):
        self._selected_index = max(0, min(index, len(self._tab_defs) - 1))
        self._render()

    def set_tab_content(self, index, content):
        """يحدّث محتوى تبويب واحد بعد إنشائه (بدون إعادة بناء الشريط كله) -
        مفيد للصفحات اللي بتبني كل تبويب لوحده عند الضغط على زرار مختلف."""
        if 0 <= index < len(self._tab_defs):
            label, _old = self._tab_defs[index]
            self._tab_defs[index] = (label, content)
            if index == self._selected_index:
                self._body.content = content
                if self.page:
                    self.page.update()

    def _render(self):
        buttons = []
        for i, (label, _content) in enumerate(self._tab_defs):
            active = i == self._selected_index
            buttons.append(
                ft.Container(
                    content=ft.Text(label, size=14, color="#FFFFFF" if active else TEXT_MUTED),
                    bgcolor=PRIMARY if active else None,
                    padding=ft.Padding(left=16, right=16, top=9, bottom=9),
                    border_radius=8,
                    ink=True,
                    on_click=lambda e, idx=i: self.select(idx),
                )
            )
        self._bar.controls = buttons
        self._body.content = self._tab_defs[self._selected_index][1] if self._tab_defs else ft.Text("")
        if self.page:
            self.page.update()


async def pick_file(page, title="اختر ملف", extensions=None, max_mb=100):
    """يخلّي المستخدم يختار ملف من جهازه (المتصفح) ويرفعه للسيرفر، وبيرجّع المسار على السيرفر (أو None لو لغى/فشل).
    لازم تتندّه بـ await جوه handler من نوع async. الملف بيتحفظ مؤقتًا في مجلد الرفع."""
    import asyncio
    from . import files as _files
    picker = ft.FilePicker()
    done = asyncio.Event()
    state = {"err": None}

    def on_upload(ev):
        if getattr(ev, "error", None):
            state["err"] = ev.error; done.set()
        elif getattr(ev, "progress", None) is not None and ev.progress >= 1:
            done.set()
    picker.on_upload = on_upload
    page.services.append(picker)
    try:
        page.update()
        kw = {"allowed_extensions": [e.lstrip(".*") for e in extensions], "file_type": ft.FilePickerFileType.CUSTOM} if extensions else {}
        res = await picker.pick_files(dialog_title=title, allow_multiple=False, **kw)
        if not res:
            return None
        f = res[0]
        if getattr(f, "size", None) and f.size > max_mb * 1024 * 1024:
            raise ValueError(f"حجم الملف أكبر من {max_mb} ميجا")
        rel = _files.make_upload_target(f.name)
        url = page.get_upload_url(rel, 600)
        await picker.upload([ft.FilePickerUploadFile(name=f.name, id=getattr(f, "id", None), upload_url=url)])
        await asyncio.wait_for(done.wait(), timeout=600)
        if state["err"]:
            raise RuntimeError(state["err"])
        return _files.upload_path(rel)
    finally:
        try:
            page.services.remove(picker); page.update()
        except Exception:
            pass


class _SDOption:
    """كائن بسيط بخاصيتَي .key و.text - عشان .options بتاعة SearchableDropdown
    تبقى متوافقة مع نفس نمط ft.dropdown.Option اللي الكود القديم بيتوقعه."""
    def __init__(self, key, text):
        self.key = key
        self.text = text


class SearchableDropdown:
    """حقل بحث واختيار (بديل لـ ft.Dropdown) - اكتب أول حروف الاسم وتظهرلك
    الخيارات المطابقة فورًا بدل التمرير في قائمة طويلة. بيستخدم عناصر Flet
    أساسية بس (TextField + Container) لتجنّب أي مشاكل توافق مع عناصر أحدث.
    نفس واجهة .value و.options و.on_change بتاعة ft.Dropdown، فمعظم الكود
    المحيط مش محتاج يتغيّر:

        sd = theme.SearchableDropdown('العميل', width=280, options=[('1','أحمد'), ('2','محمد')])
        sd.on_change = some_func
        row.controls.append(sd.control)
        ...
        print(sd.value)  # -> '1'
    """

    def __init__(self, label='', width=280, options=None, value=None, on_change=None, hint_text=None,
                 flat=False, suggestions_height=220, page=None, on_add=None, add_label='إضافة', clear_on_focus=False):
        """flat=True: شكل مسطّح لخلايا الجداول - بيفتح حوار بحث منبثق لما
        تدوس عليه بدل قايمة اقتراحات "عائمة" تحت الحقل. جرّبنا قايمة عائمة
        جوه خلايا الجدول قبل كده وطلعت بترندر في مكان غلط (بتتراكب مع صفوف
        أو أزرار تانية في الصفحة) لأن خلايا DataTable بتحصر موضعها بطريقة
        مش موثوقة - فالحوار المنبثق (نفس أسلوب كل حوارات البرنامج التانية)
        هو الحل المضمون. في غير وضع الجدول (flat=False)، القايمة بتظهر
        وتدفع المحتوى اللي تحتها لتحت زي أي حقل عادي في نموذج - وده آمن
        لأنه مش جوه جدول مزدحم.
        on_submit: بيتنده بعد الاختيار (بالضغط أو Enter جوه حوار البحث)."""
        self.label = label
        self.width = width
        self.flat = flat
        self._sug_max = suggestions_height
        self.clear_on_focus = clear_on_focus      # الضغط على حقل فيه اختيار يفضّيه عشان الكتابة تبحث من جديد (بدل ما تتلصق على الاسم القديم)
        # on_add(نص_البحث): لو اتحدد، القايمة بتعرض صف "➕ إضافة «...» جديد" لما
        # الاسم مش موجود - عشان تضيف السجل الجديد من نفس الحقل من غير ما تخرج.
        self.on_add = on_add
        self.add_label = add_label
        self._page_ref = page
        self._options = self._normalize(options or [])
        self._value = str(value) if value is not None else None
        self.on_change = on_change
        self.on_submit = None
        self._matches = []
        self._hi = 0                 # الصف المتلوّن في قايمة الاقتراحات (يتحرك بالأسهم)
        self._hi_moved = False
        self._row_ctls = []
        self._prev_kb = None
        self._lock = __import__('threading').RLock()      # الكتابة السريعة بتشغّل معالجات متوازية: القفل يمنع نتيجة قديمة تكتب فوق الجديدة
        self._dialog = None

        if flat:
            self.text_field = ft.TextField(
                label=None, width=width, hint_text=hint_text or 'دوس للاختيار...',
                read_only=True, on_click=self._open_picker,
                border=ft.InputBorder.NONE, content_padding=ft.Padding(left=6, right=6, top=6, bottom=6), text_size=13,
            )
            self.suggestions_list = None
            self.suggestions_container = None
            self.control = self.text_field
        else:
            self.text_field = ft.TextField(
                label=label, width=width, hint_text=hint_text or 'اكتب للبحث...',
                on_change=self._on_type, on_submit=self._on_submit, suffix_icon=ft.Icons.SEARCH,
                on_focus=self._on_focus, on_blur=self._on_blur,
            )
            self.suggestions_list = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
            self.suggestions_container = ft.Container(
                content=self.suggestions_list, bgcolor=CARD_BG, border_radius=8,
                border=ft.border.Border(
                    top=ft.border.BorderSide(1, BORDER_LIGHT), right=ft.border.BorderSide(1, BORDER_LIGHT),
                    bottom=ft.border.BorderSide(1, BORDER_LIGHT), left=ft.border.BorderSide(1, BORDER_LIGHT),
                ),
                visible=False, width=width, height=suggestions_height, padding=ft.Padding(left=2, right=2, top=2, bottom=2),
            )
            self.control = ft.Column([self.text_field, self.suggestions_container], spacing=0, tight=True)

        self._sync_display()

    @staticmethod
    def _normalize(opts):
        """يقبل ft.dropdown.Option، أو tuples (key, text)، أو كائنات ليها .key/.text"""
        normalized = []
        for o in opts:
            if hasattr(o, 'key') and hasattr(o, 'text'):
                normalized.append((str(o.key), o.text))
            else:
                normalized.append((str(o[0]), o[1]))
        return normalized

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._value = str(v) if v is not None else None
        self._sync_display()

    @property
    def disabled(self):
        return bool(self.text_field.disabled)

    @disabled.setter
    def disabled(self, v):
        self.text_field.disabled = bool(v)
        if v and self.suggestions_container:
            self.suggestions_container.visible = False

    @property
    def options(self):
        return [_SDOption(k, t) for k, t in self._options]

    @options.setter
    def options(self, opts):
        self._options = self._normalize(opts)
        self._sync_display()

    def _sync_display(self):
        if self._value is None:
            self.text_field.value = ''
            return
        match = next((t for k, t in self._options if k == self._value), None)
        self.text_field.value = match if match is not None else ''

    def _safe_page(self):
        if self._page_ref is not None:
            return self._page_ref
        try:
            return self.text_field.page
        except Exception:
            return None

    def _on_focus(self, e):
        page = self._safe_page()
        if self.clear_on_focus and self._value is not None and (self.text_field.value or ''):
            self.text_field.value = ''
            if page: page.update()
        if page is not None and page.on_keyboard_event != self._on_key:      # أسهم فوق/تحت وEsc أثناء ما الحقل مفتوح (بنرجّع المعالج القديم عند الخروج)
            self._prev_kb = page.on_keyboard_event
            page.on_keyboard_event = self._on_key

    def _on_blur(self, e):
        page = self._safe_page()
        if page is not None and page.on_keyboard_event == self._on_key:
            page.on_keyboard_event = self._prev_kb
        if self.clear_on_focus and self._value is not None and not (self.text_field.value or ''):
            self._sync_display()           # خرج من الحقل من غير ما يختار حاجة جديدة: نرجّع الاسم القديم
            if page: page.update()

    def _row_style(self, i):
        on = i == self._hi
        c = self._row_ctls[i]
        c.bgcolor = PRIMARY_LIGHT if on else None
        c.content.weight = ft.FontWeight.BOLD if on else None
        c.content.color = PRIMARY_TEXT if on else None

    async def _on_key(self, e):
        key = str(getattr(e, 'key', '') or '').replace(' ', '').lower()
        visible = bool(self.suggestions_container and self.suggestions_container.visible and self._matches and self._row_ctls)
        if visible and key in ('arrowdown', 'arrowup'):
            old = self._hi
            n = len(self._matches)
            self._hi = (self._hi + (1 if key == 'arrowdown' else -1)) % n
            self._hi_moved = True
            self._row_style(old); self._row_style(self._hi)
            page = self._safe_page()
            if page: page.update()
            try:
                await self.suggestions_list.scroll_to(offset=max(0, (self._hi - 2) * 40), duration=80)
            except Exception:      # noqa: BLE001
                pass
            return
        if visible and key == 'escape':
            self.suggestions_container.visible = False
            page = self._safe_page()
            if page: page.update()
            return
        prev = self._prev_kb
        if prev and prev != self._on_key:
            r = prev(e)
            if __import__('inspect').isawaitable(r):
                await r

    def _on_type(self, e):
        with self._lock:
            self._render_suggestions()

    def _render_suggestions(self):
        raw_query = (self.text_field.value or '').strip()
        query = raw_query.lower()
        if self._value is not None:
            current_text = next((t for k, t in self._options if k == self._value), None)
            if current_text != self.text_field.value:
                self._value = None  # المستخدم بدأ يعدّل النص - الاختيار اتصفّى لحد ما يختار تاني
        page = self._safe_page()
        if not query:
            self.suggestions_list.controls = []
            self._matches = []; self._row_ctls = []
            self.suggestions_container.visible = False
            if page: page.update()
            return
        matches = [(k, t) for k, t in self._options if query in _i18n.search_hay(t)][:40]
        self._matches = matches
        self._hi = 0; self._hi_moved = False
        self._row_ctls = [
            ft.Container(
                content=ft.Text(t, size=13),
                padding=ft.Padding(left=10, right=10, top=9, bottom=9), border_radius=6,
                ink=True, on_click=lambda ev, k=k, t=t: self._select(k, t),
            ) for k, t in matches
        ]
        if self._row_ctls:
            self._row_style(0)             # أول نتيجة متلوّنة (Enter بيختارها، والأسهم بتنقل اللون)
        rows = list(self._row_ctls)
        exact = any(t.strip().lower() == query for _, t in self._options)
        if self.on_add and not exact:
            rows.insert(0, ft.Container(
                content=ft.Row([ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=16, color=PRIMARY),
                                ft.Text(f'{self.add_label} "{raw_query}"', size=13, color=PRIMARY, weight=ft.FontWeight.BOLD)], spacing=6),
                padding=ft.Padding(left=10, right=10, top=9, bottom=9), bgcolor=PRIMARY_LIGHT, border_radius=6,
                ink=True, on_click=lambda ev: self._start_add()))
        if not rows:
            rows = [ft.Container(content=ft.Text('لا توجد نتائج', size=12, color=TEXT_MUTED), padding=ft.Padding(left=10, right=10, top=9, bottom=9))]
        if (self.text_field.value or '').strip().lower() != query:
            return                          # النص اتغيّر أثناء الحساب: معالج أحدث هيرسم النتيجة الصح
        self.suggestions_list.controls = rows
        self.suggestions_container.height = min(self._sug_max, len(rows) * 40 + 8)      # الارتفاع على قد النتايج بدل مساحة فاضية
        self.suggestions_container.visible = True
        if page: page.update()

    def _start_add(self):
        """بيقفل قايمة الاقتراحات وبينده on_add بالنص المكتوب (لإضافة سجل جديد)."""
        raw_query = (self.text_field.value or '').strip()
        if self.suggestions_container:
            self.suggestions_container.visible = False
            self.suggestions_list.controls = []
        page = self._safe_page()
        if page: page.update()
        if self.on_add:
            self.on_add(raw_query)

    def _on_submit(self, e):
        """Enter: لو الاختيار لسه ما اتحدّدش بيختار النتيجة المطابقة تمامًا للكود
        (الجزء قبل ' - ') وإلا أول نتيجة - وبعدها بينده on_submit."""
        if self._value is None and not self._matches and self.on_add and (self.text_field.value or '').strip():
            self._start_add()
            return
        if self._value is None and self._matches:
            q = (self.text_field.value or '').strip().lower()
            exact = None if self._hi_moved else next(((k, t) for k, t in self._matches if t.lower().split(' - ')[0].strip() == q), None)
            k, t = exact or self._matches[min(self._hi, len(self._matches) - 1)]
            self._select(k, t)
        if self.on_submit:
            self.on_submit(e)

    # ---------------------------------------------------------------- flat
    _active_dlg = None        # فيه حوار اختيار مفتوح دلوقتي (على مستوى البرنامج): التنقل التلقائي بين الحقول مينفعش يسحب الفوكس منه

    @staticmethod
    def picker_active():
        d = SearchableDropdown._active_dlg
        try:
            return bool(d is not None and d.open)
        except Exception:      # noqa: BLE001
            return False

    def _open_picker(self, e=None):
        """بديل القايمة العائمة لوضع الجدول (flat): حوار بحث منبثق - نفس
        أسلوب كل حوارات البرنامج التانية، فمضمون إنه يترندر صح فوق أي
        جدول أو عنصر تاني، بدل القايمة العائمة اللي كانت بتتراكب غلط."""
        page = self._safe_page()
        if not page or SearchableDropdown.picker_active():
            return
        # تنضيف حوارات الاختيار القديمة (المقفولة) من الصفحة - بعد ما اتقفلت فعلًا مش في نفس تحديث القفل
        try:
            page.overlay[:] = [c for c in page.overlay if not getattr(c, '_ashour_picker', False) or getattr(c, 'open', False)]
        except Exception:      # noqa: BLE001
            pass
        search_f = ft.TextField(label='ابحث بالكود أو الاسم', autofocus=True, width=360)
        results = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, height=320)
        matches_ref = {'items': []}

        def render_results(e=None):
            q = (search_f.value or '').strip().lower()
            items = [(k, t) for k, t in self._options if not q or q in _i18n.search_hay(t)][:80]
            matches_ref['items'] = items
            results.controls = [
                ft.Container(
                    content=ft.Text(t, size=13, weight=ft.FontWeight.BOLD if k == self._value else None,
                                    color=PRIMARY if k == self._value else None),
                    padding=ft.Padding(left=12, right=12, top=11, bottom=11),
                    border_radius=6, bgcolor=PRIMARY_LIGHT if k == self._value else None,
                    ink=True, on_click=lambda ev, k=k, t=t: do_select(k, t),
                ) for k, t in items
            ] or [ft.Container(content=ft.Text('لا توجد نتائج', color=TEXT_MUTED), padding=12)]
            page.update()

        def do_select(k, t):
            close(None)                      # نقفل الحوار الأول، وبعدها الاختيار (اللي بيحرّك الفوكس للحقل اللي بعده)
            self._select(k, t)
            if self.on_submit:
                self.on_submit(e)

        def on_search_submit(ev):
            q = (search_f.value or '').strip().lower()
            exact = next(((k, t) for k, t in matches_ref['items'] if t.lower().split(' - ')[0].strip() == q), None)
            pick = exact or (matches_ref['items'][0] if matches_ref['items'] else None)
            if pick:
                do_select(*pick)

        def close(ev=None):
            SearchableDropdown._active_dlg = None
            dlg.open = False
            page.update()

        search_f.on_change = render_results
        search_f.on_submit = on_search_submit
        render_results()
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(self.label or 'اختيار'),
            content=ft.Container(width=400, content=ft.Column([search_f, ft.Divider(), results], tight=True, spacing=10)),
            actions=[ft.TextButton('إلغاء', on_click=close)],
            on_dismiss=lambda ev: setattr(SearchableDropdown, '_active_dlg', None),
        )
        self._dialog = dlg
        dlg._ashour_picker = True
        SearchableDropdown._active_dlg = dlg
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    async def focus(self):
        try:
            if self.flat:
                self._open_picker()
            else:
                await self.text_field.focus()
        except Exception:
            pass

    def _select(self, key, text):
        self._value = key
        self.text_field.value = text
        if self.suggestions_container:
            self.suggestions_container.visible = False
            self.suggestions_list.controls = []
        page = self._safe_page()
        if page: page.update()
        if self.on_change:
            self.on_change(type('SDChangeEvent', (), {'control': self})())


_MIME_TYPES = {
    '.pdf': 'application/pdf',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xls': 'application/vnd.ms-excel',
    '.csv': 'text/csv',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
}




# ----------------------------------------------------------------------
# ترقيم الصفحات: الجداول الكبيرة (آلاف الصفوف × عشرات العناصر) بتخلّي واجهة Flet تهنج لإنها بتبعت كل العناصر
# للواجهة. الحل: نبني ونعرض صفحة واحدة بس (50 صف افتراضيًا) مع شريط تنقّل وحجم صفحة قابل للتغيير.
# ----------------------------------------------------------------------
PAGE_SIZE_DEFAULT = 50
PAGE_SIZES = [25, 50, 100, 200]


class PagerBar:
    """شريط التنقل: [الأولى] [السابق] صفحة 2 من 50 [التالي] [الأخيرة]  |  عرض 51-100 من 2,500  |  عدد الصفوف.
    بيظهر بس لما عدد الصفوف أكبر من حجم الصفحة."""

    def __init__(self, on_change, page=None, page_size=PAGE_SIZE_DEFAULT):
        self.on_change = on_change
        self.page = page
        self.page_size = int(page_size or PAGE_SIZE_DEFAULT)
        self.page_no = 1
        self.total = 0
        small = ft.ButtonStyle(padding=ft.Padding(left=8, right=8, top=0, bottom=0))
        self.btn_first = ft.TextButton('الأولى', style=small, on_click=lambda e: self.go(1))
        self.btn_prev = ft.TextButton('السابق', icon=ft.Icons.CHEVRON_RIGHT, style=small, on_click=lambda e: self.go(self.page_no - 1))
        self.btn_next = ft.TextButton('التالي', icon=ft.Icons.CHEVRON_LEFT, style=small, on_click=lambda e: self.go(self.page_no + 1))
        self.btn_last = ft.TextButton('الأخيرة', style=small, on_click=lambda e: self.go(self.pages()))
        self.label = ft.Text('', size=12.5, weight=ft.FontWeight.BOLD, color=PRIMARY_TEXT)
        self.info = ft.Text('', size=12, color=TEXT_MUTED)
        self.size_dd = ft.Dropdown(width=84, dense=True, text_size=12, value=str(self.page_size), content_padding=ft.Padding(left=8, right=4, top=0, bottom=0), border_color=BORDER_LIGHT,
                                   options=[ft.dropdown.Option(str(n), str(n)) for n in sorted(set(PAGE_SIZES + [self.page_size]))], on_select=self._size_changed)
        self.control = ft.Container(visible=False, padding=ft.Padding(left=4, right=4, top=2, bottom=6), content=ft.Row(
            [self.btn_first, self.btn_prev, self.label, self.btn_next, self.btn_last, ft.Container(width=10), self.info, ft.Container(expand=True), ft.Text('عدد الصفوف', size=11.5, color=TEXT_MUTED), self.size_dd],
            spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER))

    def pages(self):
        return max(1, -(-self.total // self.page_size))

    def bounds(self):
        start = (self.page_no - 1) * self.page_size
        return start, min(self.total, start + self.page_size)

    def set_total(self, total, keep_page=True):
        old = self.total
        self.total = int(total)
        if not keep_page or abs(self.total - old) > 1:
            self.page_no = 1                       # فلتر/بحث جديد = من الصفحة الأولى؛ حذف أو إضافة صف = نفس الصفحة
        self.page_no = min(max(1, self.page_no), self.pages())
        self._refresh_labels()

    def _refresh_labels(self):
        start, end = self.bounds()
        self.control.visible = self.total > self.page_size
        self.label.value = f'صفحة {self.page_no} من {self.pages()}'
        self.info.value = f'عرض {start + 1:,}-{end:,} من {self.total:,}' if self.total else ''
        self.btn_first.disabled = self.btn_prev.disabled = self.page_no <= 1
        self.btn_next.disabled = self.btn_last.disabled = self.page_no >= self.pages()

    def go(self, n):
        n = min(max(1, int(n)), self.pages())
        if n != self.page_no:
            self.page_no = n
            self._refresh_labels()
            self.on_change()

    def _size_changed(self, e):
        try:
            size = int(self.size_dd.value)
        except (TypeError, ValueError):
            return
        if size != self.page_size:
            self.page_size = size
            self.page_no = 1
            self._refresh_labels()
            self.on_change()


class RowPager(PagerBar):
    """ترقيم صفحات لأي ft.DataTable عادي: بدل table.rows = [كل الصفوف] استخدم pager.set_rows([كل الصفوف]) - بيعرض الصفحة
    الحالية بس. الشريط بيظهر لوحده فوق الجدول لما تلفّه بـ theme.h_scroll(table)."""

    def __init__(self, table, page=None, page_size=PAGE_SIZE_DEFAULT):
        super().__init__(self._render, page, page_size)
        self.table = table
        self._all = []
        table._erp_pager = self.control
        table._erp_print_rows = self._print_rows          # الطباعة بتاخد كل الصفوف مش الصفحة الحالية بس

    def set_rows(self, rows, keep_page=True):
        """صفوف جاهزة (ft.DataRow) - بنعرض الصفحة الحالية منها."""
        self._all = list(rows)
        self._items = None
        self.set_total(len(self._all), keep_page)
        self._fill()

    def set_items(self, items, builder, keep_page=True):
        """الأسرع: عناصر خام + دالة بتبني الصف - بنبني صفوف الصفحة الحالية بس (50-100 صف) مش كل الآلاف."""
        self._items = list(items)
        self._builder = builder
        self._all = []
        self.set_total(len(self._items), keep_page)
        self._fill()

    def _fill(self):
        start, end = self.bounds()
        if getattr(self, '_items', None) is not None:
            self.table.rows = [self._builder(x) for x in self._items[start:end]]
        else:
            self.table.rows = self._all[start:end]

    def _render(self):
        self._fill()
        if self.page:
            try:
                self.page.update()
            except Exception:
                pass

    def _print_rows(self):
        if getattr(self, '_items', None) is not None:
            return [self._builder(x) for x in self._items]
        return list(self._all)

    @property
    def all_rows(self):
        return self._all


class SortableDataTable:
    """جدول بيانات قابل للفرز - دوس على عنوان أي عمود ليترتب تصاعديًا،
    ودوس تاني لينعكس تنازليًا (زي أي جدول في برامج المكاتب). الاستخدام:

        t = theme.SortableDataTable(
            columns=[('الاسم', lambda r: r.name), ('الرصيد', lambda r: r.balance, True)],
            row_builder=lambda r: ft.DataRow(cells=[...]),
        )
        t.set_data(rows)                 # قايمة العناصر الخام (مش ft.DataRow)
        some_layout = ft.Column([..., t.control, ...])

    columns: [(عنوان, دالة_مفتاح_الفرز أو None لعمود مش قابل للفرز)] أو
             (عنوان, دالة_مفتاح_الفرز, numeric) لو العمود رقمي (محاذاة صح).
    دالة مفتاح الفرز بترجع القيمة المُستخدمة في المقارنة (نص/رقم/تاريخ)."""

    def __init__(self, columns, row_builder, page=None, initial_sort=None, initial_ascending=True, page_size=PAGE_SIZE_DEFAULT, **table_kwargs):
        self._specs = [(c[0], c[1], c[2] if len(c) > 2 else False) for c in columns]
        self._row_builder = row_builder
        self.page = page
        self.paged = bool(page_size)
        self.pager = PagerBar(self._render_page_change, page, page_size or PAGE_SIZE_DEFAULT)
        self._data = []
        self._sort_index = None
        self._ascending = initial_ascending
        data_columns = [
            ft.DataColumn(ft.Text(label), numeric=numeric, on_sort=(self._make_sort_handler(i) if key is not None else None))
            for i, (label, key, numeric) in enumerate(self._specs)
        ]
        self.control = ft.DataTable(columns=data_columns, rows=[], **table_kwargs)
        # نسخة تانية من الجدول (نفس الأعمدة والصفوف = نفس العرض بالظبط) بتتقصّ لعنوان الجدول بس وبتتحط فوق الجدول: عنوان ثابت
        # لما تسكرول الصفوف (راجع h_scroll). الضغط على العنوان فيها بيفرز زي الأصلي.
        clone_columns = [ft.DataColumn(ft.Text(label), numeric=numeric, on_sort=(self._make_sort_handler(i) if key is not None else None))
                         for i, (label, key, numeric) in enumerate(self._specs)]
        self.clone = ft.DataTable(columns=clone_columns, rows=[], **table_kwargs)
        self.control._erp_sticky = self.clone
        self.control._erp_print_rows = lambda: [self._row_builder(i) for i in self._sorted_data()]
        if self.paged:
            self.control._erp_pager = self.pager.control       # theme.h_scroll بيحط الشريط فوق الجدول
        if initial_sort is not None:
            self._sort_index = initial_sort

    def _make_sort_handler(self, index):
        def handler(e):
            asc = getattr(e, 'data', None)
            if asc is not None:
                self._ascending = str(asc).lower() != 'false'
            elif self._sort_index == index:
                self._ascending = not self._ascending
            else:
                self._ascending = True
            self._sort_index = index
            self._render()
        return handler

    def _sorted_data(self):
        if self._sort_index is None:
            return self._data
        key = self._specs[self._sort_index][1]
        if key is None:
            return self._data

        def safe_key(item):
            try:
                v = key(item)
            except Exception:
                v = None
            if v is None:
                return (0, '')
            if isinstance(v, (int, float)):
                return (1, v)
            if isinstance(v, (datetime.datetime, datetime.date)):
                return (1, v)
            return (1, str(v).lower())
        return sorted(self._data, key=safe_key, reverse=not self._ascending)

    def _render_page_change(self):
        self._render(reset=False)

    def _render(self, reset=None):
        data = self._sorted_data()
        if self.paged:
            if reset is None:
                self.pager.set_total(len(data))
            else:
                self.pager.set_total(len(data), keep_page=True)
            start, end = self.pager.bounds()
            data = data[start:end]          # بنبني صفحة واحدة بس (50 صف) بدل الآلاف
        self.control.rows = [self._row_builder(item) for item in data]
        self.clone.rows = [self._row_builder(item) for item in data]
        for _t in (self.control, self.clone):
            _style_rows(_t.rows)                 # صفوف متبادلة اللون + تمييز عند المرور
        self.control.sort_column_index = self._sort_index
        self.control.sort_ascending = self._ascending
        self.clone.sort_column_index = self._sort_index
        self.clone.sort_ascending = self._ascending
        if self.page:
            try:
                self.page.update()
            except Exception:
                pass

    def set_data(self, data):
        """يحدّث بيانات الجدول (قايمة عناصر خام) ويعيد الترتيب بنفس عمود
        الفرز الحالي - استخدمها بدل ما تحطّ .rows مباشرة."""
        self._data = list(data)
        self._render()

    @property
    def data(self):
        return self._sorted_data()


def _style_rows(rows):
    """صفوف متبادلة اللون (أسهل في تتبّع الصف) وتمييز الصف اللي الماوس عليه. الصف اللي ليه لون من الشاشة نفسها (مثلًا حسابات رئيسية) بيفضل زي ما هو."""
    for i, r in enumerate(rows):
        if getattr(r, 'color', None) is None:
            r.color = {ft.ControlState.HOVERED: PRIMARY_LIGHT, ft.ControlState.DEFAULT: ROW_BG[i % 2]}


def _page_width_now(page=None):
    try:
        if page is None:
            from flet.controls.context import _context_page
            page = _context_page.get(None)
        w = float(getattr(page, 'width', 0) or 0)
        return w if w > 0 else 0.0
    except Exception:
        return 0.0


def _cell_width(c, depth=0):
    """تقدير عرض محتوى خلية بالبكسل (نص / أزرار أيقونات / صفوف وأعمدة / شارات)."""
    if c is None or depth > 6:
        return 0.0
    if isinstance(c, ft.Text):
        return min(len(c.value or ''), 40) * 6.4
    if isinstance(c, ft.TextField):
        return float(c.width or 160)
    if isinstance(c, (ft.IconButton,)):
        return 40.0
    if isinstance(c, (ft.TextButton, ft.OutlinedButton, ft.FilledButton, ft.ElevatedButton)):
        return 110.0
    if isinstance(c, ft.Icon):
        return 24.0
    if isinstance(c, ft.Checkbox):
        return 40.0
    kids = getattr(c, 'controls', None)
    if isinstance(kids, list):
        ws = [_cell_width(k, depth + 1) for k in kids]
        if isinstance(c, ft.Row):
            return sum(ws) + (float(getattr(c, 'spacing', 0) or 0)) * max(0, len(ws) - 1)
        return max(ws or [0.0])
    inner = getattr(c, 'content', None)
    pad = 0.0
    if isinstance(c, ft.Container):
        pd = getattr(c, 'padding', None)
        try:
            pad = float((getattr(pd, 'left', 0) or 0) + (getattr(pd, 'right', 0) or 0)) if pd is not None and not isinstance(pd, (int, float)) else (2 * float(pd or 0))
        except Exception:
            pad = 0.0
        w = getattr(c, 'width', None)
        if isinstance(w, (int, float)):
            return float(w)
    return _cell_width(inner, depth + 1) + pad if inner is not None else 0.0


def _fit_columns(table, clone, specs, page=None):
    """بيوزّع أعمدة الجدول على عرض الكارت: الجدول في فلت بياخد عرض محتواه بس (فبيسيب فراغ كبير على الشاشات العريضة)،
    فنكبّر المسافة بين الأعمدة بقدر الفراغ (من 22 لحد 120 بكسل) بتقدير لعرض المحتوى من أطول نص في كل عمود."""
    try:
        W = _page_width_now(page)
        if W < 900 or len(specs) < 4:                         # موبايل/نافذة ضيقة: الجداول بتتحوّل كروت أو بتتمرّر أفقيًا
            return
        n = len(specs)
        est = 0.0
        for ci, (label, _k, _num) in enumerate(specs):
            head_w = len(str(label)) * 5.0 + 12
            widest = 0.0
            for r in (table.rows or [])[:25]:
                try:
                    widest = max(widest, _cell_width(r.cells[ci].content) if ci < len(r.cells) else 0.0)
                except Exception:
                    pass
            est += max(head_w, widest) + 8
        avail = W - 64 - 56 - 40                          # الشريط الجانبي + هوامش الصفحة + حشوة الكارت
        gap = max(22.0, min(120.0, (avail - est - 2 * 14) / max(1, n - 1)))
        for t in (table, clone):
            if t is not None:
                t.column_spacing = gap
    except Exception:
        pass


def _fit_table(table):
    """توزيع الأعمدة لجدول خام (مش SortableDataTable) متعلّم بـ _erp_fit (جدول في كارت بعرض الصفحة)."""
    try:
        specs = [(_ctl_text(c.label) or '', None, False) for c in table.columns]
        _fit_columns(table, table.__dict__.get('_erp_clone') or getattr(table, '_erp_sticky', None), specs, None)
    except Exception:
        pass


def fit_page_tables(root):
    """بعد بناء شاشة: الجداول اللي في محتوى الصفحة نفسه (مش جوه نوافذ - النوافذ في overlay) بيتوزّع عرض أعمدتها على عرض الصفحة."""
    tables, clones, seen = [], set(), set()

    def walk(c, depth=0):
        if c is None or id(c) in seen or depth > 60 or isinstance(c, (str, int, float)):
            return
        seen.add(id(c))
        if isinstance(c, ft.DataTable):
            tables.append(c)
            return
        for a in ('controls', 'content'):
            v = getattr(c, a, None)
            for x in (v if isinstance(v, list) else [v]):
                walk(x, depth + 1)
    try:
        walk(root)
        for t in tables:
            for cl in (t.__dict__.get('_erp_clone'), getattr(t, '_erp_sticky', None)):
                if cl is not None:
                    clones.add(id(cl))
        for t in tables:
            if id(t) in clones:
                continue
            t.__dict__['_erp_fit'] = True
            _fit_table(t)
    except Exception:
        pass


def launch_url(page, url):
    """يفتح رابطًا. page.launch_url مغلّف بـ @deprecated فلا يُعتبر coroutine، لذا نغلّفه بدالة async."""
    async def _go():
        r = page.launch_url(url)
        if hasattr(r, '__await__'):
            await r
    page.run_task(_go)


def open_or_download_file(page, path):
    """يبعت للمتصفح رابط تنزيل مؤقت لملف اتعمل على السيرفر (PDF/Excel/نسخة...). الرابط بيتمسح تلقائي بعد شوية."""
    try:
        from . import files as _files
        launch_url(page, _files.publish_download(path))
    except Exception as ex:
        try:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر تجهيز التنزيل: {ex}'), open=True)); page.update()
        except Exception:
            pass


# ----------------------------------------------------------------------
# عنوان جدول ثابت لأي جدول (ft.DataTable): نسخة من الأعمدة والصفوف بنفس العرض بالظبط بتتقصّ لعنوان الجدول وتتثبّت فوقه (راجع h_scroll)
# ----------------------------------------------------------------------
import dataclasses as _dc
from flet.controls.base_control import BaseControl as _BaseControl

PAGE_HEIGHT = 800            # ارتفاع نافذة البرنامج (main.py بيحدّثه) - بيحدّد أقصى ارتفاع لمنطقة الجدول
_ROW_EST = 52                # تقدير ارتفاع صف الجدول (لحساب ارتفاع المنطقة لما الجدول قصير)
_CLONE_TABLE_FIELDS = ('heading_row_height', 'data_row_min_height', 'data_row_max_height', 'column_spacing', 'horizontal_margin', 'divider_thickness', 'show_checkbox_column',
                       'checkbox_horizontal_margin', 'heading_row_color', 'bgcolor', 'show_bottom_border', 'border', 'sort_column_index', 'sort_ascending', 'on_select_all', 'clip_behavior')


_CLONE_FIELDS = {}


def _clone_fields(cls):
    r = _CLONE_FIELDS.get(cls)
    if r is None:
        r = _CLONE_FIELDS[cls] = [f for f in _dc.fields(cls) if f.init and not f.name.startswith('_')]
    return r


def clone_control(obj):
    """نسخة نضيفة (معرّفات جديدة) من أي عنصر Flet وأبنائه - بتعيد بناءه من حقول الإنشاء. أحداث الضغط بتفضل نفس الدوال."""
    if isinstance(obj, _BaseControl):
        kwargs = {}
        for f in _clone_fields(type(obj)):
            val = getattr(obj, f.name)
            if val is None and f.default is None:
                continue                          # القيمة الافتراضية: مفيش داعي نمررها (أسرع كتير في نسخ آلاف الخلايا)
            if isinstance(val, (str, int, float, bool)) and f.default is not _dc.MISSING and val == f.default:
                continue
            if isinstance(val, (list, tuple, dict)) and not val and f.default_factory is not _dc.MISSING:
                continue
            kwargs[f.name] = clone_control(val)
        return type(obj)(**kwargs)
    if isinstance(obj, list):
        return [clone_control(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(clone_control(x) for x in obj)
    return obj


_orig_table_setattr = ft.DataTable.__setattr__


def _table_setattr(self, name, value):
    if name == 'rows' and isinstance(value, list):
        _style_rows(value)                         # صفوف متبادلة وتمييز عند المرور لكل الجداول (الجداول الخام كمان)
    _orig_table_setattr(self, name, value)
    if name == 'rows' and self.__dict__.get('_erp_fit'):
        _fit_table(self)
    if name == 'columns' and isinstance(value, list):       # تغيير أعمدة الجدول (تجميع/مقارنة): نسخة العنوان الثابت لازم تتبعه
        clone = self.__dict__.get('_erp_clone')
        if clone is not None:
            try:
                clone.columns = [ft.DataColumn(label=clone_control(c.label), numeric=c.numeric, tooltip=c.tooltip, heading_row_alignment=c.heading_row_alignment, on_sort=c.on_sort) for c in value]
            except Exception:
                pass
    if name in ('rows', 'sort_column_index', 'sort_ascending'):
        clone = self.__dict__.get('_erp_clone')
        if clone is not None:
            try:
                if name == 'rows':
                    clone.rows = clone_control(value)
                else:
                    setattr(clone, name, value)
            except Exception:
                pass          # فشل نسخ عنصر غريب: العنوان الثابت بس يفضل بالصفوف القديمة - الجدول الأصلي مش بيتأثر
        if name == 'rows':
            for cb in self.__dict__.get('_erp_on_rows', ()):
                try:
                    cb(value)
                except Exception:
                    pass


ft.DataTable.__setattr__ = _table_setattr


def _make_header_clone(table):
    cols = [ft.DataColumn(label=clone_control(c.label), numeric=c.numeric, tooltip=c.tooltip, heading_row_alignment=c.heading_row_alignment, on_sort=c.on_sort) for c in table.columns]
    kwargs = {k: getattr(table, k) for k in _CLONE_TABLE_FIELDS if getattr(table, k, None) is not None}
    clone = ft.DataTable(columns=cols, rows=[], **kwargs)
    clone.rows = clone_control(table.rows)
    table._erp_clone = clone             # من هنا أي table.rows = [...] بيتنسخ تلقائي للنسخة
    return clone


def _is_compact_page():
    """الصفحة (الجلسة) الحالية على شاشة موبايل؟ بنقراها من سياق Flet وقت بناء الشاشة. أي حاجة غير True (اختبارات، MagicMock) = شاشة عادية."""
    try:
        from flet.controls.context import _context_page
        return getattr(_context_page.get(None), '_erp_compact', False) is True
    except Exception:
        return False


def _ctl_text(c):
    v = getattr(c, 'value', None)
    if isinstance(v, str):
        return v
    return ''


class _CardTable:
    """موبايل: بيعرض ft.DataTable كقايمة كروت (كل صف = كارت: الأول عنوان، والباقي «اسم العمود: القيمة»، وأزرار الإجراءات تحت).
    بيتحدّث تلقائي لما table.rows تتغيّر (نفس الخطّاف بتاع العنوان الثابت). أزرار/عناصر الخلايا هي نفسها (مش نسخ) فكل أحداثها شغالة."""
    ACTION_LABELS = ('الإجراءات', 'إجراءات', 'اجراءات', '')

    def __init__(self, table):
        self.table = table
        self.col = ft.Column(spacing=8)
        table.__dict__.setdefault('_erp_on_rows', []).append(self.rebuild)
        self.rebuild(table.rows)

    def _is_action(self, label, cell):
        c = cell.content
        if label.strip() in self.ACTION_LABELS and not _ctl_text(c):
            return True
        kids = getattr(c, 'controls', None)
        return bool(kids) and all(isinstance(k, (ft.IconButton, ft.TextButton, ft.OutlinedButton, ft.FilledButton, ft.PopupMenuButton)) for k in kids)

    def rebuild(self, rows):
        heads = [_ctl_text(c.label) for c in self.table.columns]
        cards = []
        for r in (rows or []):
            title, body, actions = None, [], []
            for i, cell in enumerate(r.cells):
                label = heads[i] if i < len(heads) else ''
                c = cell.content
                if c is None:
                    continue
                if self._is_action(label, cell):
                    actions.append(c)
                elif title is None:
                    title = ft.Container(c, padding=ft.Padding(left=0, right=0, top=0, bottom=4))
                else:
                    if isinstance(c, ft.Text) and (c.value or '').strip() in ('', '-'):
                        continue
                    body.append(ft.Row([ft.Container(ft.Text(label, size=11, color=TEXT_MUTED), width=96),
                                        ft.Container(c, expand=True)], vertical_alignment=ft.CrossAxisAlignment.START, spacing=6))
            controls = ([title] if title is not None else []) + body
            if actions:
                controls.append(ft.Row(actions, wrap=True, spacing=4, alignment=ft.MainAxisAlignment.START))
            cards.append(ft.Container(ft.Column(controls, spacing=4), padding=12, border_radius=12, bgcolor=SURFACE_ALT,
                                      border=(lambda b: ft.border.Border(top=b, bottom=b, left=b, right=b))(ft.border.BorderSide(1, BORDER_LIGHT))))
        self.col.controls = cards
        if not cards:
            self.col.controls = [ft.Text('لا توجد بيانات', color=TEXT_MUTED, size=12)]


def _sort_picker(table):
    """قايمة ترتيب للموبايل (العناوين القابلة للفرز مش ظاهرة في الكروت)."""
    import types
    cols = [(i, c) for i, c in enumerate(table.columns) if c.on_sort is not None]
    if not cols:
        return None
    dd = ft.Dropdown(label='ترتيب حسب', dense=True, border_radius=10, text_size=13, width=200,
                     options=[ft.dropdown.Option(key=str(i), text=_ctl_text(c.label)) for i, c in cols])

    def changed(e):
        try:
            cols_by_i = dict(cols)
            cols_by_i[int(dd.value)].on_sort(types.SimpleNamespace(data=None))
        except Exception:
            pass
    dd.on_change = changed
    return dd


def h_scroll(content, step=420, vscroll=None):
    """يلفّ أي محتوى عريض (جدول غالبًا) بتمرير أفقي + شريط أسهم فوقه.
    شريط التمرير الأفقي الأصلي بيظهر بس تحت الجدول (يعني لازم تنزل لآخر
    الصفحة)، فالأسهم (◀ ▶) دي بتخليك تتحرك يمين وشمال من فوق مباشرة، وفيه
    كمان قفز لأقصى اليمين/اليسار. كمان Shift + عجلة الماوس بتحرّك أفقيًا.
    اتجاه الأسهم بيراعي RTL: التمرير بيبدأ من اليمين، فالتحرك لليسار =
    زيادة الإزاحة."""
    row = ft.Row([content], scroll=ft.ScrollMode.AUTO)
    target = {'row': row}        # الـRow اللي بيتحرّك فعليًا (في وضع العنوان الثابت بيتبدّل بـ sticky_row)
    pager_bar = getattr(content, '_erp_pager', None)

    def _is_rtl(e):
        try:
            return bool(getattr(e.control.page, 'rtl', True))
        except Exception:
            return True

    def _signed(e, toward_left):
        # RTL: أقصى اليمين = إزاحة 0، وكل تحرك لليسار بيزوّد الإزاحة
        return step if (toward_left == _is_rtl(e)) else -step

    async def scroll_left(e):
        try:
            await target['row'].scroll_to(delta=_signed(e, True), duration=250)
        except Exception:
            pass

    async def scroll_right(e):
        try:
            await target['row'].scroll_to(delta=_signed(e, False), duration=250)
        except Exception:
            pass

    async def jump_left(e):
        try:
            # لليسار في RTL = نهاية المحتوى (offset=-1)، وفي LTR = البداية
            await target['row'].scroll_to(offset=(-1 if _is_rtl(e) else 0), duration=300)
        except Exception:
            pass

    async def jump_right(e):
        try:
            await target['row'].scroll_to(offset=(0 if _is_rtl(e) else -1), duration=300)
        except Exception:
            pass

    def grab(r):
        # السحب بالماوس اتلغى (كان بطيء على الجداول الكبيرة): التمرير بالأسهم أو Shift + عجلة الماوس
        return r

    bar = ft.Row(
        [
            ft.IconButton(icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT, tooltip='أقصى اليسار', icon_size=18, on_click=jump_left),
            ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_LEFT, tooltip='تمرير لليسار', icon_size=20, on_click=scroll_left),
            ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_RIGHT, tooltip='تمرير لليمين', icon_size=20, on_click=scroll_right),
            ft.IconButton(icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT, tooltip='أقصى اليمين', icon_size=18, on_click=jump_right),
            ft.Text('تمرير أفقي (أو Shift + عجلة الماوس)', size=11, color=TEXT_MUTED),
        ],
        spacing=0, alignment=ft.MainAxisAlignment.START,
    )
    if isinstance(content, ft.DataTable) and _is_compact_page() and (getattr(content, '_erp_sticky', None) is not None or getattr(content, '_erp_pager', None) is not None):
        cards = _CardTable(content)
        try:
            from flet.controls.context import _context_page
            _context_page.get(None)._erp_cards_used = True
        except Exception:
            pass
        sp = _sort_picker(content)
        cards.col._erp_src_table = content          # الطباعة تقرا الجدول الأصلي حتى في وضع الكروت (موبايل)
        return ft.Column(([pager_bar] if pager_bar is not None else []) + ([sp] if sp is not None else []) + [cards.col], spacing=8)
    is_table = isinstance(content, ft.DataTable)
    sticky = None
    if is_table and vscroll is not False:
        # عنوان الجدول ثابت وهو بيسكرول: الجدول الأصلي جوه عمود بيسكرول رأسيًا، وفوقه (Stack) نسخة مقصوصة لعنوانه بس بنفس العرض.
        try:
            sticky = getattr(content, '_erp_sticky', None) or _make_header_clone(content)
        except Exception:
            sticky = None
    if is_table and vscroll is not False and sticky is None:
        is_table = False          # تعذّر عمل نسخة العنوان: نكمّل بالشكل القديم من غير عنوان ثابت (آمن)
    if is_table and vscroll is not False:
        head_h = (getattr(content, 'heading_row_height', None) or 56) + 1
        overlay = ft.Container(content=sticky, height=head_h, clip_behavior=ft.ClipBehavior.HARD_EDGE, bgcolor=CARD_BG, top=0, left=0)
        stack = ft.Stack([ft.Column([content], scroll=ft.ScrollMode.AUTO, spacing=0), overlay])
        sticky_row = ft.Row([stack], scroll=ft.ScrollMode.AUTO, expand=True)
        sticky_row._erp_vbody = True
        sticky_area = grab(sticky_row)
        target['row'] = sticky_row          # أسهم التمرير لازم تحرّك الـRow الفعلي (كانت بتحرّك Row مش ظاهر فمبتشتغلش)
        top = ([pager_bar] if pager_bar is not None else []) + [bar]
        if vscroll:           # داخل كارت ممدود (الصفحة نفسها ما بتسكرولش): المنطقة بتاخد باقي الارتفاع
            return ft.Column(top + [sticky_area], spacing=0, expand=True)
        # داخل صفحة بتسكرول أو حوار: منطقة بارتفاع محسوب (حسب عدد الصفوف وارتفاع النافذة) وسكرولها الخاص + العنوان ثابت
        max_h = max(260, min(640, int(PAGE_HEIGHT or 800) - 430))
        region = ft.Container(height=max_h, content=ft.Column([sticky_area], spacing=0))

        def fit(rows):
            n = len(rows or [])
            region.height = min(max_h, max(head_h + 90, head_h + n * _ROW_EST + 8))
        fit(content.rows)
        content.__dict__.setdefault('_erp_on_rows', []).append(fit)
        return ft.Column(top + [region], spacing=0)
    if vscroll:
        # جدول جوه كارت ممدود (expand): الصفحة نفسها مش بتسكرول، فبنعمل سكرول رأسي للصفوف وسيب الشريط (الترقيم + الأسهم) ثابت فوق
        body = ft.Column([grab(row)], scroll=ft.ScrollMode.AUTO, expand=True, spacing=0)
        body._erp_vbody = True            # علامة لأدوات الفحص
        return ft.Column(([pager_bar] if pager_bar is not None else []) + [bar, body], spacing=0, expand=True)
    return ft.Column(([pager_bar] if pager_bar is not None else []) + [bar, grab(row)], spacing=0)


# ======================================================================
# حماية من الضغط المتكرر على أزرار الحفظ والتأكيد (منع تكرار الفواتير والسندات)
# ======================================================================
import os as _os
import threading as _threading
import time as _time
import inspect as _inspect

SUBMIT_COOLDOWN = float(_os.environ.get('ERP_SUBMIT_COOLDOWN', '1.5'))   # ثواني بعد كل تنفيذ بنتجاهل فيها أي ضغطة زيادة (بالاختبارات = 0)
SUBMIT_BUSY_TEXT = 'جاري التنفيذ...'


def guard_submit_button(button, owner=None, busy_text=None):
    """بيلفّ on_click بتاع زرار حفظ/تأكيد بحماية من الضغط المتكرر:
    - الزرار بيتعطّل ويتغيّر نصه لـ"جاري التنفيذ..." أول ما تضغط (فيظهر للمستخدم إن العملية شغالة).
    - أي ضغطة تانية وقت التنفيذ (حتى لو على خيط تاني) بتتجاهل.
    - ضغطات الدبل-كليك المتأخرة بتتجاهل لثواني قليلة بعد انتهاء التنفيذ.
    - لو حصل خطأ والحوار فاضل مفتوح، الزرار بيرجع شغال تاني."""
    handler = getattr(button, 'on_click', None)
    if not callable(handler) or getattr(handler, '_erp_guarded', False):
        return
    busy_text = busy_text or SUBMIT_BUSY_TEXT
    lock = _threading.Lock()
    state = {'last': 0.0}

    def refresh_ui():
        try:
            pg = getattr(owner, 'page', None) if owner is not None else None
            pg = pg or getattr(button, 'page', None)
            if pg:
                pg.update()
        except Exception:
            pass

    def begin():
        if SUBMIT_COOLDOWN and (_time.monotonic() - state['last']) < SUBMIT_COOLDOWN:
            return None
        if not lock.acquire(blocking=False):
            return None
        saved = (button.content, button.disabled)
        button.disabled = True
        if isinstance(button.content, str):
            button.content = busy_text
        refresh_ui()
        return saved

    def end(saved):
        # منرجّعش النص القديم لو الدالة نفسها غيّرت نص الزرار (زي زرار بيتحول من حفظ لتعديل)
        if button.content == busy_text:
            button.content = saved[0]
        button.disabled = saved[1]
        state['last'] = _time.monotonic()
        lock.release()
        refresh_ui()

    if _inspect.iscoroutinefunction(handler):
        async def wrapper(e=None):
            saved = begin()
            if saved is None:
                return
            try:
                await handler(e)
            finally:
                end(saved)
    else:
        def wrapper(e=None):
            saved = begin()
            if saved is None:
                return
            try:
                return handler(e)
            finally:
                end(saved)
    wrapper._erp_guarded = True
    button.on_click = wrapper


def guard_submit(button, owner=None, busy_text=None):
    """زي guard_submit_button بس بيرجّع الزرار نفسه - عشان تلفّ بيه الزرار وقت إنشائه:
        theme.guard_submit(ft.FilledButton('حفظ', on_click=save))"""
    guard_submit_button(button, owner, busy_text)
    return button


def install_submit_guard():
    """بيفعّل الحماية تلقائيًا على كل أزرار FilledButton الموجودة في actions بتاعة أي
    AlertDialog (أزرار الحفظ/التأكيد/التقديم...) من غير ما نعدّل كل شاشة لوحدها."""
    if getattr(ft.AlertDialog, '_erp_submit_guard', False):
        return
    original_init = ft.AlertDialog.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            for act in (self.actions or []):
                if isinstance(act, ft.FilledButton):
                    guard_submit_button(act, owner=self)
        except Exception:
            pass

    ft.AlertDialog.__init__ = patched_init
    ft.AlertDialog._erp_submit_guard = True


install_submit_guard()


# ----------------------------------------------------------------------
# Row(wrap=True) مع عنصر expand بيطلّع مربع رمادي (Flutter: Wrap مبيدعمش Flexible). بدل ما نصلّح الشاشات واحدة واحدة (وأي شاشة جديدة
# هتكرر الغلط)، قبل كل تحديث بنشيل expand من أبناء أي Row بيلفّ.
# ----------------------------------------------------------------------
def _drop_expand_in_wrap(row):
    if getattr(row, 'wrap', False):
        for c in (row.__dict__.get('controls') or []):
            if getattr(c, 'expand', None):
                try:
                    c.expand = None
                except Exception:
                    pass


_orig_row_before_update = ft.Row.before_update
_orig_row_setattr = ft.Row.__setattr__


def _row_before_update(self):
    _orig_row_before_update(self)
    _drop_expand_in_wrap(self)
    try:
        _compact_fix(self)
    except Exception:
        pass


def _row_setattr(self, name, value):
    _orig_row_setattr(self, name, value)
    if name in ('controls', 'wrap'):
        _drop_expand_in_wrap(self)


ft.Row.before_update = _row_before_update
ft.Row.__setattr__ = _row_setattr


# ----------------------------------------------------------------------
# تجاوب الموبايل العام: قبل كل تحديث لأي عنصر على صفحة موبايل (عرضها < 760):
#  - أي عنصر عرضه الثابت أكبر من الشاشة بيتصغّر لعرض الشاشة.
#  - أي صف (Row) أعرض من الشاشة ومفيهوش تمرير ولا عنصر ممدود بيبقى بيلفّ لسطر تاني.
# بيتنفّذ لكل التحديثات (حوارات، قوائم بتتبني بعد التحميل...) مش بس بناء الشاشة الأول. على الكمبيوتر مفيش أي تغيير.
# ----------------------------------------------------------------------
from flet.controls.base_control import BaseControl as _BC
_orig_bc_before_update = _BC.before_update


def _page_w():
    try:
        from flet.controls.context import _context_page
        pg = _context_page.get(None)
        if pg is not None and getattr(pg, '_erp_compact', False) is True:
            return float(getattr(pg, 'width', 0) or 0)
    except Exception:
        pass
    return 0.0


def _est_w(c):
    w = getattr(c, 'width', None)
    if isinstance(w, (int, float)):
        return float(w)
    if isinstance(c, ft.IconButton):
        return 44.0
    if isinstance(c, ft.Text):
        return len(c.value or '') * float(getattr(c, 'size', None) or 14) * 0.62 + 4
    if isinstance(c, ft.Row) or isinstance(c, ft.Column):
        return 160.0
    return 90.0


def _compact_fix(self):
    w = _page_w()
    if not w:
        return
    lim = w - 32
    if lim <= 100 or any(k.__name__ in ('Page', 'BasePage') for k in type(self).__mro__):
        return              # الصفحة نفسها لها width (عرض النافذة): مفيش لمس
    kids0 = self.__dict__.get('controls')
    one = self.__dict__.get('content')
    for c in list(kids0 or []) + ([one] if one is not None and hasattr(one, '__dataclass_fields__') else []) + [self]:
        cw = getattr(c, 'width', None)
        if isinstance(cw, (int, float)) and cw > lim and not getattr(c, '_erp_nocap', False):
            try:
                c.width = lim
            except Exception:
                pass
    if isinstance(self, ft.Row) and not getattr(self, 'wrap', False) and not getattr(self, 'scroll', None) and not self.__dict__.get('_erp_nowrap'):
        for c in (self.__dict__.get('controls') or []):       # فواصل فاضية (Container expand من غير محتوى): على الموبايل بتتشال عشان الصف يقدر يلفّ
            if isinstance(c, ft.Container) and c.expand and c.content is None:
                try:
                    c.visible = False
                except Exception:
                    pass
        kids = [c for c in (self.__dict__.get('controls') or []) if getattr(c, 'visible', True) is not False]
        if len(kids) > 1 and not any(getattr(c, 'expand', None) for c in kids) and sum(_est_w(c) for c in kids) > lim:
            try:
                self.wrap = True
                self.run_spacing = 6
            except Exception:
                pass
    if isinstance(self, ft.Row) and getattr(self, 'wrap', False):
        for c in (self.__dict__.get('controls') or []):      # حقول النماذج في صف ملفوف: بعرض الشاشة كلها عشان تتراصّ بدل ما تتبعثر بمقاسات مختلفة
            cw = getattr(c, 'width', None)
            if isinstance(c, (ft.TextField, ft.Dropdown)) and isinstance(cw, (int, float)) and 150 <= cw < lim:
                try:
                    c.width = lim
                except Exception:
                    pass
            elif isinstance(c, ft.Column) and len(c.controls or []) == 2 and isinstance(c.controls[0], ft.TextField):      # قايمة البحث (SearchableDropdown): الحقل + قايمة الاقتراحات
                tf, sg = c.controls
                if isinstance(tf.width, (int, float)) and 150 <= tf.width < lim:
                    try:
                        tf.width = lim
                        if isinstance(getattr(sg, 'width', None), (int, float)):
                            sg.width = lim
                    except Exception:
                        pass


def _field_defaults(self):
    """شكل موحّد لكل حقول الإدخال والقوائم: حواف مدوّرة وحدّ هادئ (بس لو الشاشة ما حدّدتش غيره)."""
    if isinstance(self, (ft.TextField, ft.Dropdown)):
        if getattr(self, "border_radius", None) is None:
            self.border_radius = 10
        if getattr(self, "border_color", None) is None:
            self.border_color = "#4A4666" if DARK else "#CFCFE0"
        if getattr(self, "focused_border_color", None) is None:
            self.focused_border_color = PRIMARY


_GLYPH_FIX = {"\u2192": "-", "\u2190": "-", "\u25b2": "+", "\u25bc": "-", "\u25a0": "="}   # رموز مش موجودة في خط Cairo بتظهر مربعات


def _fix_glyphs(self):
    if isinstance(self, ft.Text):
        v = getattr(self, "value", None)
        if isinstance(v, str) and any(g in v for g in _GLYPH_FIX):
            for g, r in _GLYPH_FIX.items():
                v = v.replace(g, r)
            self.value = v


def _bc_before_update(self):
    _orig_bc_before_update(self)
    try:
        _fix_glyphs(self)
    except Exception:
        pass
    try:
        _field_defaults(self)
    except Exception:
        pass
    try:
        _compact_fix(self)
    except Exception:
        pass
    try:
        from . import i18n
        i18n.translate_control(self)
    except Exception:
        pass


_BC.before_update = _bc_before_update


# ---------------------------------------------------------------------------
# فرز تلقائي لأي جدول عادي (ft.DataTable): الضغط على عنوان العمود يرتّب الصفوف
# تصاعديًا وتاني ضغطة تنازليًا. الجداول اللي عندها فرز (SortableDataTable) أو
# معلّمة _erp_nosort مبتتغيرش.
# ---------------------------------------------------------------------------
def _cell_text(ctrl, depth=0):
    """أول نص/قيمة حقل جوه خلية (Text / TextField / أي حاوية فيها واحد منهم)."""
    if ctrl is None or depth > 6:
        return None
    if isinstance(ctrl, (ft.Text, ft.TextField)):
        v = ctrl.value
        return '' if v is None else str(v)
    if isinstance(ctrl, ft.Checkbox):
        return '1' if ctrl.value else '0'
    for attr in ('content', 'controls', 'label'):
        v = getattr(ctrl, attr, None)
        for c in (v if isinstance(v, list) else [v]):
            r = _cell_text(c, depth + 1) if c is not None and not isinstance(c, str) else None
            if r not in (None, ''):
                return r
    return None


def _sort_key_value(text):
    t = (text or '').strip()
    if not t:
        return (2, 0.0, '')
    num = t.replace(',', '').replace('%', '').replace('ر.س', '').strip()
    try:
        return (0, float(num), '')
    except ValueError:
        pass
    import re as _re
    m = _re.match(r'^(\d{1,4})[-/](\d{1,2})[-/](\d{1,4})', t)         # تواريخ yyyy-mm-dd أو dd/mm/yyyy
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y, mo, d = (a, b, c) if a > 31 else (c, b, a)
        return (0, y * 10000 + mo * 100 + d, '')
    return (1, 0.0, t.lower())


def enable_table_sorting(table):
    """بيركّب معالج الفرز على أعمدة الجدول (لازم يتنادى قبل أول رسم - راجع الباتش تحت)."""
    cols = table.columns
    if not cols or getattr(table, '_erp_nosort', False) or any(c.on_sort for c in cols):
        return
    state = {'index': None, 'asc': True}

    def make(i):
        def handler(e):
            state['asc'] = (not state['asc']) if state['index'] == i else True
            state['index'] = i

            def key(row):
                try:
                    return _sort_key_value(_cell_text(row.cells[i].content))
                except Exception:
                    return (2, 0.0, '')
            ordered = sorted(table.rows, key=key, reverse=not state['asc'])
            fresh = [clone_control(r) for r in ordered]       # نسخ جديدة من الصفوف (معرّفات جديدة)
            hook = getattr(table, '_erp_row_replaced', None)
            if hook:
                for old_r, new_r in zip(ordered, fresh):
                    hook(old_r, new_r)
            table.rows = fresh
            table.sort_column_index = i
            table.sort_ascending = state['asc']
            try:
                table.page.update()
            except Exception as ex:      # noqa: BLE001
                import sys
                print('table sort update failed:', repr(ex), file=sys.stderr)
        return handler

    for i, c in enumerate(cols):
        label = c.label
        if isinstance(label, ft.Text) and (label.value or '').strip():
            c.on_sort = make(i)


# لازم الفرز يتركّب وقت إنشاء الجدول (قبل أول رسم) - لو اتركّب جوه before_update الأحداث
# بتشتغل بس تحديث الصفوف مبيوصلش للمتصفح. فبنلف __init__ بتاع DataTable.
_orig_dt_init = ft.DataTable.__init__


def _dt_init(self, *args, **kwargs):
    _orig_dt_init(self, *args, **kwargs)
    try:
        enable_table_sorting(self)
    except Exception:      # noqa: BLE001
        pass


ft.DataTable.__init__ = _dt_init



# ======================= الشاشات المنبثقة الموحّدة =======================
_ERR_WORDS = ('تعذر', 'خطأ', 'فشل', 'لا يمكن', 'لازم', 'غير صحيح', 'ممنوع', 'مرفوض', 'error', 'failed', 'cannot', 'invalid')
_OK_WORDS = ('تم ', 'تمت', 'اتحفظ', 'اتسجل', 'اتضاف', 'اتحذف', 'اتنسخ', 'saved', 'done')


def _snack_kind(text, data=None):
    if data in _NOTIFY_STYLE:
        return data
    t = (text or '').lower()
    if any(w in t for w in _ERR_WORDS):
        return 'error'
    if any(t.startswith(w) or w in t[:12] for w in _OK_WORDS):
        return 'success'
    return 'info'


def _style_snackbars():
    """كل ft.SnackBar في البرنامج (150+ مكان) بياخد شكل موحّد: لون وأيقونة حسب النوع، والخطأ بيفضل أطول. النوع بيتحدد من
    data='error|success|warning|info' لو اتحدد، وإلا من نص الرسالة. أي SnackBar فيه bgcolor صريح بيتساب زي ما هو."""
    if getattr(ft.SnackBar, '_erp_styled', False):
        return
    orig = ft.SnackBar.__init__

    def init(self, content=None, *a, **k):
        if isinstance(content, ft.Text) and k.get('bgcolor') is None:
            kind = _snack_kind(content.value, k.get('data'))
            color, icon, secs = _NOTIFY_STYLE[kind]
            content = ft.Row([ft.Icon(icon, color='#FFFFFF', size=18), ft.Text(content.value, color='#FFFFFF', expand=True, selectable=True)], spacing=8)
            k['bgcolor'] = color
            k.setdefault('duration', secs * 1000)
        orig(self, content, *a, **k)
    ft.SnackBar.__init__ = init
    ft.SnackBar._erp_styled = True



def _open_dialogs(page):
    return [c for c in list(getattr(page, 'overlay', None) or []) if isinstance(c, ft.AlertDialog) and getattr(c, 'open', False)]


def close_top_dialog(page):
    """بيقفل آخر نافذة منبثقة مفتوحة (للضغط على Esc). بيرجّع True لو قفل حاجة."""
    ds = _open_dialogs(page)
    if not ds:
        return False
    ds[-1].open = False
    try:
        page.update()
    except Exception:      # noqa: BLE001
        pass
    return True


def install_dialog_keys(page):
    """Esc يقفل النافذة المنبثقة المفتوحة في أي شاشة (بدل ما تفضل مقفولة modal من غير مخرج)."""
    prev = {'h': page.on_keyboard_event}

    def on_key(e):
        if getattr(e, 'key', '') == 'Escape' and close_top_dialog(page):
            return
        h = prev['h']
        if h and h is not on_key:
            h(e)
    page.on_keyboard_event = on_key
    return on_key


def confirm(page, title, message, on_yes, yes_label='تأكيد', no_label='تراجع', danger=True, icon=None):
    """نافذة تأكيد موحّدة للعمليات الخطيرة (حذف/إلغاء): أيقونة + رسالة واضحة + زرار أحمر للخطر.
    on_yes() بيتنفّذ بعد ما النافذة تتقفل؛ لو رمى استثناء بنعرضه في SnackBar خطأ بدل ما يضيع."""
    done = {'busy': False}

    def close(e=None):
        dlg.open = False
        page.update()

    def yes(e):
        if done['busy']:        # منع الضغط المزدوج
            return
        done['busy'] = True
        close()
        try:
            on_yes()
        except Exception as ex:      # noqa: BLE001
            notify(page, str(ex), 'error')
    color = DANGER if danger else PRIMARY
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([ft.Icon(icon or (ft.Icons.WARNING_AMBER_ROUNDED if danger else ft.Icons.HELP_OUTLINE), color=color), ft.Text(title, weight=ft.FontWeight.BOLD)], spacing=8),
        content=ft.Container(ft.Text(message, size=14), width=380),
        actions=[ft.TextButton(no_label, on_click=close), ft.FilledButton(yes_label, bgcolor=color, on_click=yes)],
        actions_alignment=ft.MainAxisAlignment.END)
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
    return dlg


_NOTIFY_STYLE = {'success': ('#1B7F5C', ft.Icons.CHECK_CIRCLE_OUTLINE, 3), 'error': ('#C62828', ft.Icons.ERROR_OUTLINE, 8),
                 'warning': ('#B26A00', ft.Icons.WARNING_AMBER_ROUNDED, 5), 'info': ('#37474F', ft.Icons.INFO_OUTLINE, 4)}


def notify(page, message, kind='info'):
    """رسالة سريعة موحّدة بلون وأيقونة حسب النوع (success/error/warning/info). الخطأ بيفضل أطول عشان يتقري."""
    color, icon, secs = _NOTIFY_STYLE.get(kind, _NOTIFY_STYLE['info'])
    sb = ft.SnackBar(ft.Row([ft.Icon(icon, color='#FFFFFF', size=18), ft.Text(str(message), color='#FFFFFF', expand=True)], spacing=8),
                     bgcolor=color, duration=secs * 1000, open=True)
    page.overlay.append(sb)
    page.update()
    return sb


# ---- أزرار الأيقونات: tooltip تلقائي بالمعنى الموحّد لو مفيش tooltip (أزرار أيقونة من غير نص بتتفهم من التلميح) ----
_ICON_TIPS = {
    'DELETE_OUTLINE': 'حذف', 'DELETE': 'حذف', 'DELETE_SWEEP_OUTLINED': 'حذف الكل', 'EDIT_OUTLINED': 'تعديل', 'EDIT': 'تعديل',
    'VISIBILITY_OUTLINED': 'عرض', 'VISIBILITY': 'عرض', 'PRINT_OUTLINED': 'طباعة', 'PRINT': 'طباعة', 'SAVE_OUTLINED': 'حفظ',
    'CLOSE': 'إغلاق', 'ADD': 'إضافة', 'ADD_CIRCLE_OUTLINE': 'إضافة', 'REFRESH': 'تحديث', 'DOWNLOAD': 'تحميل', 'UNDO': 'تراجع',
    'CONTENT_COPY': 'نسخ', 'SEARCH': 'بحث', 'KEYBOARD_ARROW_DOWN': 'فتح/قفل', 'KEYBOARD_ARROW_UP': 'فتح/قفل',
    'PICTURE_AS_PDF': 'تصدير PDF', 'TABLE_VIEW': 'تصدير Excel', 'ATTACH_FILE': 'إرفاق ملف', 'MORE_VERT': 'المزيد', 'INFO_OUTLINE': 'معلومات',
}


def _tip_icon_buttons():
    if getattr(ft.IconButton, '_erp_tips', False):
        return
    orig = ft.IconButton.__init__

    def init(self, icon=None, *a, **k):
        if k.get('tooltip') is None and icon is None:
            icon = k.pop('icon', None)
        if k.get('tooltip') is None and icon is not None:
            name = getattr(icon, 'name', None) or str(icon).split('.')[-1]
            tip = _ICON_TIPS.get(str(name).upper())
            if tip:
                k['tooltip'] = tip
        orig(self, icon, *a, **k)
    ft.IconButton.__init__ = init
    ft.IconButton._erp_tips = True


# ---- الأرقام السالبة في خلايا الجداول بتتلوّن أحمر تلقائيًا (رصيد دائن/عجز) من غير تعديل كل شاشة ----
_NEG_RE = __import__('re').compile(r'^\(?-\s?\d[\d,]*(\.\d+)?\)?$')


def _color_negative_cells():
    if getattr(ft.DataCell, '_erp_neg', False):
        return
    orig = ft.DataCell.__init__

    def init(self, content=None, *a, **k):
        if isinstance(content, ft.Text) and content.color is None and isinstance(content.value, str) and _NEG_RE.match(content.value.strip()):
            content.color = DANGER
        orig(self, content, *a, **k)
    ft.DataCell.__init__ = init
    ft.DataCell._erp_neg = True


def empty_state(text='لا توجد بيانات', icon=None, hint=None):
    """حالة "فاضي" موحّدة: أيقونة كبيرة باهتة + رسالة + تلميح اختياري."""
    kids = [ft.Icon(icon or ft.Icons.INBOX_OUTLINED, size=40, color=TEXT_MUTED), ft.Text(text, size=14, color=TEXT_MUTED, weight=ft.FontWeight.W_600)]
    if hint:
        kids.append(ft.Text(hint, size=12, color=TEXT_MUTED))
    return card(ft.Column(kids, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6), padding=28)


_style_snackbars()
_tip_icon_buttons()
_color_negative_cells()
