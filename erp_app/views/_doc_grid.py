"""جدول سطور مستند (شكل Excel - نفس تصميم جداول الفواتير) قابل للضبط بالأعمدة: بيستخدمه التوالف وتحويل المخازن وأوامر التصنيع.
أنواع الأعمدة: index (رقم)، product (اختيار صنف)، qty (كمية)، acct (اختيار حساب)، static (نص محسوب بيتحدّث من الشاشة)، delete."""
import flet as ft
from .. import theme
from ._invoice_grid import _cell, _num, _to_float


class _DocLine:
    def __init__(self, grid):
        self.grid = grid
        self.w = {}
        self.product_obj = None
        g = grid
        widgets, widths = [], []
        for col in g.columns:
            kind, key, width = col['kind'], col['key'], col['width']
            widths.append(width)
            if kind == 'index':
                w = ft.Text('', size=12, color=theme.TEXT_MUTED, text_align=ft.TextAlign.CENTER)
            elif kind == 'product':
                w = theme.SearchableDropdown(label=col['title'], width=width - 6, options=g._options, flat=True, hint_text='اكتب كود أو اسم الصنف ثم Enter', suggestions_height=180, page=g.page)
                w.on_change = self._on_product
                w.on_submit = lambda e: g.focus(self.qty_field)
            elif kind == 'qty':
                w = _num(width - 6, on_change=self._on_qty, on_submit=lambda e: g.next_line(self))
            elif kind == 'acct':
                w = theme.SearchableDropdown(label=col['title'], width=width - 6, options=g.acct_options, flat=True, hint_text=col.get('hint', 'افتراضي'), suggestions_height=180, page=g.page, value='')
                w.on_change = lambda e=None: g._changed()
            elif kind == 'static':
                w = ft.Text('', size=12.5, text_align=ft.TextAlign.CENTER, no_wrap=False)
            elif kind == 'delete':
                w = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, icon_size=18, tooltip='حذف السطر', on_click=lambda e: g.remove_line(self))
            else:
                raise ValueError(kind)
            self.w[key] = w
            widgets.append(w)
        cells = []
        for col, w, wd in zip(g.columns, widgets, widths):
            ctrl = w.control if col['kind'] in ('product', 'acct') else w
            cell = _cell(ctrl, wd)
            if col['kind'] in ('index', 'static'):
                cell.content = ft.Container(content=ctrl, alignment=ft.Alignment(0, 0))
            cells.append(cell)
        self.control = ft.Container(content=ft.Row(cells, spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                    border=ft.border.Border(bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT), right=ft.border.BorderSide(1, theme.BORDER_LIGHT)))
        self.qty_field = next((self.w[c['key']] for c in g.columns if c['kind'] == 'qty'), None)

    # ---- قيم
    @property
    def product_id(self):
        v = next((self.w[c['key']].value for c in self.grid.columns if c['kind'] == 'product'), None)
        return int(v) if v else None

    @property
    def qty(self):
        return _to_float(self.qty_field.value) if self.qty_field is not None else 0.0

    @property
    def account_id(self):
        for c in self.grid.columns:
            if c['kind'] == 'acct':
                v = self.w[c['key']].value
                return int(v) if v else None
        return None

    def set_static(self, key, text, color=None, tooltip=None):
        t = self.w[key]
        t.value = text
        t.color = color
        self.w[key].tooltip = tooltip

    def _on_product(self, e=None):
        g = self.grid
        pid = self.product_id
        self.product_obj = g.products.get(str(pid)) if pid else None
        if not self.product_obj:
            return
        if self.qty_field is not None and not (self.qty_field.value or '').strip():
            self.qty_field.value = '1'
        g._line_changed(self)
        if self is g.lines[-1]:
            g.add_line()          # دايمًا فيه سطر فاضي جاهز في الآخر
        g.focus(self.qty_field)

    def _on_qty(self, e=None):
        self.grid._line_changed(self)


class DocGrid:
    def __init__(self, page, columns, on_line=None, on_change=None, rows_height=300, acct_options=None):
        self.page = page
        self.columns = columns
        self.on_line = on_line            # on_line(line): بعد تغيّر صنف/كمية السطر - الشاشة بتحدّث الأعمدة static
        self.on_change = on_change        # على أي تغيير (للملخص)
        self.acct_options = acct_options or []
        self._options = []
        self.products = {}
        self.lines = []
        header = ft.Container(
            content=ft.Row([_cell(ft.Text(c['title'] if c['kind'] != 'delete' else '', size=12, weight=ft.FontWeight.BOLD), c['width'], header=True) for c in columns], spacing=0),
            bgcolor=theme.SURFACE_ALT, border=ft.border.Border(top=ft.border.BorderSide(1, theme.BORDER_LIGHT), bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT), right=ft.border.BorderSide(1, theme.BORDER_LIGHT)))
        self.rows_col = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, height=rows_height)
        self.add_btn = ft.OutlinedButton('إضافة سطر', icon=ft.Icons.ADD, on_click=lambda e: self.add_line(focus=True))
        self.control = ft.Column([header, self.rows_col, ft.Row([self.add_btn])], spacing=4)
        self.add_line()

    def set_products(self, products):
        self.products = {str(p.id): p for p in products}
        self._options = [(str(p.id), f'{p.sku} - {p.name}') for p in products]
        for ln in self.lines:
            for c in self.columns:
                if c['kind'] == 'product':
                    ln.w[c['key']].options = self._options

    def add_line(self, focus=False):
        ln = _DocLine(self)
        self.lines.append(ln)
        self.rows_col.controls.append(ln.control)
        self._renumber()
        if focus:
            self.open_product(ln)
        return ln

    def remove_line(self, line):
        if line in self.lines:
            self.lines.remove(line); self.rows_col.controls.remove(line.control)
        if not self.lines:
            self.add_line()
        self._renumber(); self._changed()

    def clear(self):
        self.lines.clear(); self.rows_col.controls.clear()
        self.add_line(); self._changed()

    def _renumber(self):
        for i, ln in enumerate(self.lines):
            for c in self.columns:
                if c['kind'] == 'index':
                    ln.w[c['key']].value = str(i + 1)
            ln.control.bgcolor = theme.ROW_BG[i % 2]

    def recalc_all(self):
        """إعادة حساب أعمدة كل السطور (لما يتغيّر المخزن أو أي حاجة في الرأس)."""
        for ln in self.lines:
            if ln.product_id:
                ln.product_obj = self.products.get(str(ln.product_id))
                if self.on_line:
                    self.on_line(ln)
        self._changed()

    async def _focus(self, ctrl):
        try:
            await ctrl.focus()
        except Exception:
            pass

    def focus(self, ctrl):
        if ctrl is None:
            return
        try:
            self.page.run_task(self._focus, ctrl)
        except Exception:
            pass

    def open_product(self, line):
        for c in self.columns:
            if c['kind'] == 'product':
                line.w[c['key']]._open_picker()
                return

    def next_line(self, line):
        """Enter بعد الكمية = اختيار صنف السطر اللي بعده (وبيتضاف سطر جديد لو ده آخر واحد)."""
        i = self.lines.index(line)
        if i + 1 < len(self.lines):
            self.open_product(self.lines[i + 1])
        else:
            self.open_product(self.add_line()); self.page.update()

    def _line_changed(self, line):
        if self.on_line and line.product_id:
            self.on_line(line)
        self._changed()

    def _changed(self):
        if self.on_change:
            self.on_change()

    def get_items(self):
        """سطور المستند للحفظ: [{product_id, quantity, account_id}] - بيرمي ValueError برقم السطر لو فيه خطأ."""
        items = []
        for n, ln in enumerate(self.lines, 1):
            if not ln.product_id:
                if ln.qty_field is not None and (ln.qty_field.value or '').strip():
                    raise ValueError(f'السطر {n}: اختر الصنف')
                continue
            if ln.qty <= 0:
                raise ValueError(f'السطر {n}: الكمية يجب أن تكون أكبر من صفر')
            items.append({'product_id': ln.product_id, 'quantity': ln.qty, 'damage_account_id': ln.account_id})
        return items


def doc_datetime(date_text, end_of_day=False):
    """تاريخ المستند (نص YYYY-MM-DD من حقل التاريخ) -> datetime. اليوم الحالي بيحتفظ بالوقت الفعلي، وأي يوم تاني الساعة 12:00."""
    import datetime
    now = datetime.datetime.now()
    if not (date_text or '').strip():
        raise ValueError('حدد تاريخ المستند')
    try:
        d = datetime.datetime.strptime(date_text.strip(), '%Y-%m-%d').date()
    except ValueError:
        raise ValueError('تاريخ المستند غير صحيح')
    if d == now.date():
        return datetime.datetime.combine(d, now.time())
    return datetime.datetime.combine(d, datetime.time(23, 59, 0) if end_of_day else datetime.time(12, 0))


def end_of_day(date_text):
    """نهاية اليوم (23:59:59) - لحساب الرصيد في تاريخ معيّن (بيشمل كل حركات اليوم ده)."""
    import datetime
    d = datetime.datetime.strptime(date_text.strip(), '%Y-%m-%d').date()
    return datetime.datetime.combine(d, datetime.time(23, 59, 59))
