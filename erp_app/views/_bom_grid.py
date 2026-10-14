"""جدول مكونات الصنف (شكل Excel - نفس تصميم جداول الفواتير): كل سطر = مكوّن + وحدة + كمية + تكلفة الوحدة + الإجمالي.
الوحدة بتتختار من وحدات المكوّن (كرتونة، كيلو...) والكمية بتتسجّل بالوحدة المختارة وبتتحوّل للأساسية عند الحفظ."""
import flet as ft
from .. import services, theme
from ._invoice_grid import _cell, _num, _to_float

COLS = [('#', 34), ('المكوّن', 330), ('الوحدة', 130), ('الكمية', 110), ('تكلفة الوحدة', 130), ('الإجمالي', 130), ('', 46)]


class _BomLine:
    def __init__(self, grid):
        self.grid = grid
        self.unit_lines = {}
        g = grid
        self.index = ft.Text('', size=12, color=theme.TEXT_MUTED, text_align=ft.TextAlign.CENTER)
        self.product = theme.SearchableDropdown(label='المكوّن', width=COLS[1][1] - 6, options=g._options, flat=True,
                                                hint_text='اكتب كود أو اسم المكوّن ثم Enter', suggestions_height=180, page=g.page)
        self.product.on_change = self._on_product
        self.product.on_submit = lambda e: g.focus(self.qty)
        self.unit = ft.Dropdown(width=COLS[2][1] - 6, options=[], border=ft.InputBorder.NONE, content_padding=ft.Padding(left=4, right=4, top=6, bottom=6), text_size=13)
        self.unit.on_change = self._recalc
        self.qty = _num(COLS[3][1] - 6, on_change=self._recalc, on_submit=lambda e: g.next_line(self))
        self.unit_cost = ft.Text('', size=13, color=theme.TEXT_MUTED, text_align=ft.TextAlign.CENTER)
        self.total = ft.Text('', size=13, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
        self.remove_btn = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, icon_size=18, tooltip='حذف السطر', on_click=lambda e: g.remove_line(self))
        widgets = [self.index, self.product.control, self.unit, self.qty, self.unit_cost, self.total, self.remove_btn]
        cells = [_cell(w, COLS[i][1]) for i, w in enumerate(widgets)]
        for i in (0, 4, 5):
            cells[i].content = ft.Container(content=widgets[i], alignment=ft.Alignment(0, 0))
        self.control = ft.Container(content=ft.Row(cells, spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                    border=ft.border.Border(bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT), right=ft.border.BorderSide(1, theme.BORDER_LIGHT)))

    # ---- اختيار المكوّن: وحداته + الوحدة الافتراضية
    def set_component(self, product_id, unit_id=None):
        p = self.grid._products.get(str(product_id))
        if not p:
            return
        self.product.value = str(product_id)
        lines = services.list_product_units(p.id)
        self.unit_lines = {str(l.unit_id): l for l in lines}
        self.unit.options = [ft.dropdown.Option(str(l.unit_id), l.unit.name) for l in lines]
        default = next((l for l in lines if l.is_default), lines[0] if lines else None)
        chosen = str(unit_id) if unit_id and str(unit_id) in self.unit_lines else (str(default.unit_id) if default else None)
        self.unit.value = chosen
        if not lines:
            self.unit.options = [ft.dropdown.Option('', p.unit or 'قطعة')]
            self.unit.value = ''

    def _on_product(self, e=None):
        g = self.grid
        pid = self.product.value
        if not pid:
            return
        self.set_component(pid)
        if not (self.qty.value or '').strip():
            self.qty.value = '1'
        self._recalc()
        if self is g.lines[-1]:
            g.add_line()          # دايمًا فيه سطر فاضي جاهز في الآخر
        g.focus(self.qty)

    def _factor(self):
        l = self.unit_lines.get(self.unit.value or '')
        return float(l.factor_to_base or 1) if l else 1.0

    def calc(self):
        p = self.grid._products.get(self.product.value or '')
        if not p:
            return 0.0, 0.0
        unit_cost = (p.cost_price or 0) * self._factor()
        return unit_cost, unit_cost * _to_float(self.qty.value)

    def _recalc(self, e=None):
        if self.product.value:
            uc, tot = self.calc()
            self.unit_cost.value = f'{uc:,.2f}'
            self.total.value = f'{tot:,.2f}'
        else:
            self.unit_cost.value = self.total.value = ''
        self.grid._changed()


class BomLinesGrid:
    def __init__(self, page, on_change=None, rows_height=300):
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
        ln = _BomLine(self)
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

    def load(self, bom_lines):
        """تعبئة الجدول من مكونات محفوظة (list_bom_lines)."""
        self.lines.clear(); self.rows_col.controls.clear()
        for bl in bom_lines:
            ln = self.add_line()
            if str(bl.component_id) not in self._products:
                self._products[str(bl.component_id)] = bl.component
                self._options.append((str(bl.component_id), f'{bl.component.sku} - {bl.component.name}'))
            ln.set_component(bl.component_id, bl.unit_id)
            ln.qty.value = f'{(bl.unit_qty if bl.unit_qty else bl.quantity):g}'
            ln._recalc()
        self.add_line()               # سطر فاضي جاهز في الآخر
        self._renumber(); self._changed()

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
        try:
            self.page.run_task(self._focus, ctrl)
        except Exception:
            pass

    def open_product(self, line):
        line.product._open_picker()

    def next_line(self, line):
        """Enter بعد الكمية = اختيار مكوّن السطر اللي بعده (وبيتضاف سطر جديد لو ده آخر واحد)."""
        i = self.lines.index(line)
        if i + 1 < len(self.lines):
            self.open_product(self.lines[i + 1])
        else:
            self.open_product(self.add_line()); self.page.update()

    def _changed(self):
        if self.on_change:
            self.on_change()

    def summary(self):
        n = 0; cost = 0.0
        for ln in self.lines:
            if ln.product.value:
                n += 1; cost += ln.calc()[1]
        return n, cost

    def get_items(self):
        """سطور المكونات للحفظ - بيرمي ValueError برقم السطر لو فيه قيمة غلط."""
        items = []
        for n, ln in enumerate(self.lines, 1):
            if not ln.product.value:
                if (ln.qty.value or '').strip():
                    raise ValueError(f'السطر {n}: اختر المكوّن')
                continue
            qty = _to_float(ln.qty.value)
            if qty <= 0:
                raise ValueError(f'السطر {n}: الكمية يجب أن تكون أكبر من صفر')
            items.append({'component_id': int(ln.product.value), 'quantity': qty, 'unit_id': int(ln.unit.value) if ln.unit.value else None})
        return items
