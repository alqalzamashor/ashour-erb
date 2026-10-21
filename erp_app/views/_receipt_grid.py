"""جدول أصناف سند استلام المشتريات (شكل Excel - نفس تصميم جدول فاتورة المشتريات):
كل سطر = صنف + وحدة (من وحدات الصنف: قطعة، كرتون...) + كمية مستلمة + تكلفة الوحدة التقديرية + الإجمالي."""
import flet as ft
from .. import theme
from .. import services
from ._invoice_grid import _cell, _num, _to_float, BatchRow

COLS = [('#', 34), ('الصنف', 330), ('الوحدة', 130), ('الكمية المستلمة', 130), ('تكلفة الوحدة (تقديرية)', 160), ('الإجمالي', 140), ('', 46)]


class _ReceiptLine:
    def __init__(self, grid):
        self.grid = grid
        g = grid
        self.index = ft.Text('', size=12, color=theme.TEXT_MUTED, text_align=ft.TextAlign.CENTER)
        self.product = theme.SearchableDropdown(label='الصنف', width=COLS[1][1] - 6, options=g._options, flat=True,
                                                hint_text='اكتب كود أو اسم الصنف ثم Enter', suggestions_height=180, page=g.page)
        self.product.on_change = self._on_product
        self.product.on_submit = lambda e: g.focus(self.qty)
        self.unit = ft.Dropdown(width=COLS[2][1] - 6, options=[], border=ft.InputBorder.NONE, content_padding=ft.Padding(left=4, right=4, top=6, bottom=6), text_size=13)
        self.unit.on_change = self._on_unit
        self.unit_lines = {}          # unit_id -> سطر وحدة الصنف (معامل التحويل وتكلفة الوحدة)
        self._prev_factor = 1.0
        self.qty = _num(COLS[3][1] - 6, on_change=self._recalc, on_submit=lambda e: g.focus(self.cost))
        self.cost = _num(COLS[4][1] - 6, on_change=self._recalc, on_submit=lambda e: g.next_line(self))
        self.total = ft.Text('', size=13, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
        self.remove_btn = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, icon_size=18, tooltip='حذف السطر',
                                        on_click=lambda e: g.remove_line(self))
        widgets = [self.index, self.product.control, self.unit, self.qty, self.cost, self.total, self.remove_btn]
        cells = [_cell(w, COLS[i][1]) for i, w in enumerate(widgets)]
        for i in (0, 5):
            cells[i].content = ft.Container(content=widgets[i], alignment=ft.Alignment(0, 0))
        self.batch_row = BatchRow()
        self.control = ft.Container(content=ft.Column([ft.Row(cells, spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER), self.batch_row.control], spacing=0),
                                    border=ft.border.Border(bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT), right=ft.border.BorderSide(1, theme.BORDER_LIGHT)))

    def _on_product(self, e=None):
        g = self.grid
        p = g._products.get(self.product.value or '')
        if not p:
            return
        lines = services.list_product_units(p.id)
        self.unit_lines = {str(l.unit_id): l for l in lines}
        self.unit.options = [ft.dropdown.Option(str(l.unit_id), l.unit.name) for l in lines] or [ft.dropdown.Option('', p.unit or 'قطعة')]
        default = next((l for l in lines if l.is_default), lines[0] if lines else None)
        self.unit.value = str(default.unit_id) if default else ''
        self._prev_factor = float(default.factor_to_base or 1) if default else 1.0
        self.batch_row.apply_product(p, services.is_batch_tracked(p))
        if not (self.cost.value or '').strip():
            self.cost.value = f'{((default.cost_price if default and default.cost_price else (p.cost_price or 0) * self._prev_factor)):g}'
        if not (self.qty.value or '').strip():
            self.qty.value = '1'
        self._recalc()
        if self is g.lines[-1]:
            g.add_line()          # دايمًا فيه سطر فاضي جاهز في الآخر
        g.focus(self.qty)

    def _on_unit(self, e=None):
        """تغيير وحدة الاستلام: تكلفة الوحدة بتتحوّل بنسبة معامل الوحدة الجديدة للقديمة (نفس التكلفة للوحدة الأساسية)، والكمية بتفضل زي ما كتبتها."""
        line = self.unit_lines.get(self.unit.value or '')
        new_factor = float(line.factor_to_base or 1) if line else 1.0
        if (self.cost.value or '').strip():
            self.cost.value = f'{_to_float(self.cost.value) * new_factor / (self._prev_factor or 1.0):g}'
        self._prev_factor = new_factor
        self._recalc()

    def calc(self):
        return _to_float(self.qty.value) * _to_float(self.cost.value)

    def _recalc(self, e=None):
        self.total.value = f'{self.calc():,.2f}' if self.product.value else ''
        self.grid._changed()


class ReceiptLinesGrid:
    def __init__(self, page, on_change=None, rows_height=290):
        self.page = page
        self.on_change = on_change
        self._options = []
        self._products = {}
        self.lines = []
        header = ft.Container(
            content=ft.Row([_cell(ft.Text(t, size=12, weight=ft.FontWeight.BOLD), w, header=True) for t, w in COLS], spacing=0),
            bgcolor=theme.SURFACE_ALT, border=ft.border.Border(top=ft.border.BorderSide(1, theme.BORDER_LIGHT), bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT), right=ft.border.BorderSide(1, theme.BORDER_LIGHT)))
        self.rows_col = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, height=rows_height)
        self.add_btn = ft.OutlinedButton('إضافة سطر', icon=ft.Icons.ADD, on_click=lambda e: self.add_line(focus=True))
        self.control = ft.Column([header, self.rows_col, ft.Row([self.add_btn])], spacing=4)
        self.add_line()

    def set_products(self, products):
        self._products = {str(p.id): p for p in products}
        self._options = [(str(p.id), f'{p.sku} - {p.name}') for p in products]
        for ln in self.lines:
            ln.product.options = self._options

    def add_line(self, focus=False):
        ln = _ReceiptLine(self)
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
            ln.index.value = str(i + 1)
            ln.control.bgcolor = theme.ROW_BG[i % 2]

    async def _focus(self, ctrl):
        try:
            await ctrl.focus()
        except Exception:
            pass

    def focus(self, ctrl):
        if getattr(self, '_loading', False):
            return
        try:
            self.page.run_task(self._focus, ctrl)
        except Exception:
            pass

    def open_product(self, line):
        """بيفتح اختيار الصنف للسطر (نفس أسلوب باقي شبكات الفواتير)."""
        line.product._open_picker()

    def next_line(self, line):
        """Enter بعد التكلفة = اختيار صنف السطر اللي بعده (وبيتضاف سطر جديد لو ده آخر واحد)."""
        i = self.lines.index(line)
        if i + 1 < len(self.lines):
            self.open_product(self.lines[i + 1])
        else:
            self.open_product(self.add_line()); self.page.update()

    def _changed(self):
        if self.on_change:
            self.on_change()

    def summary(self):
        n = qty = cost = 0.0
        for ln in self.lines:
            if ln.product.value:
                n += 1; qty += _to_float(ln.qty.value); cost += ln.calc()
        return int(n), qty, cost

    def snapshot(self):
        """لقطة خام للسطور (من غير تحقق) للحفظ التلقائي كمسودة - بترجع بنفس شكل load_items."""
        out = []
        for ln in self.lines:
            if ln.product.value:
                out.append({'product_id': ln.product.value, 'unit_id': ln.unit.value or None, 'quantity': ln.qty.value or '', 'unit_cost': ln.cost.value or '',
                            'expiry': ln.batch_row.expiry.value or '', 'batch_no': ln.batch_row.batch.value or ''})
        return out

    def load_items(self, items):
        """استرجاع سطور مسودة محفوظة (الأصناف اللي مش موجودة دلوقتي بتتجاهل)."""
        self._loading = True
        try:
            self.lines.clear(); self.rows_col.controls.clear()
            for it in items:
                if str(it.get('product_id')) not in self._products:
                    continue
                ln = self.add_line()
                ln.qty.value = str(it.get('quantity') or ''); ln.cost.value = str(it.get('unit_cost') or '')
                ln.product.value = str(it['product_id'])
                ln._on_product()                      # بيجهّز الوحدات وصف الصلاحية من غير ما يمسح الكمية/التكلفة
                if it.get('unit_id') and str(it['unit_id']) in ln.unit_lines:
                    ln.unit.value = str(it['unit_id'])
                    ln._prev_factor = float(ln.unit_lines[str(it['unit_id'])].factor_to_base or 1)
                if it.get('expiry'):
                    ln.batch_row.expiry.value = it['expiry']
                ln.batch_row.batch.value = it.get('batch_no') or ''
                ln._recalc()
            self.lines[:] = [l for l in self.lines if l.product.value]
            self.rows_col.controls[:] = [l.control for l in self.lines]
            self.add_line()
            self._renumber(); self._changed()
        finally:
            self._loading = False

    def get_items(self):
        """سطور السند للحفظ - بيرمي ValueError برقم السطر لو فيه قيمة غلط."""
        items = []
        for n, ln in enumerate(self.lines, 1):
            if not ln.product.value:
                continue
            qty = _to_float(ln.qty.value)
            if qty <= 0:
                raise ValueError(f'السطر {n}: الكمية يجب أن تكون أكبر من صفر')
            cost = _to_float(ln.cost.value)
            if cost < 0:
                raise ValueError(f'السطر {n}: التكلفة لا يمكن أن تكون سالبة')
            exp, batch_no = ln.batch_row.values(n)
            items.append({'product_id': int(ln.product.value), 'quantity': qty, 'unit_cost': cost, 'unit_id': int(ln.unit.value) if ln.unit.value else None, 'expiry_date': exp, 'batch_no': batch_no})
        return items
