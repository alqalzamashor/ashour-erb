"""جدول سطور فاتورة مشتريات الأصول (شكل Excel - نفس تصميم جدول فاتورة المشتريات):
كل سطر = أصل (اسم + فئة + كمية + تكلفة الوحدة + ضريبة + عمر + قيمة تخريدية)."""
import flet as ft
from .. import services, theme
from ._invoice_grid import _cell, _num, _to_float

# (العنوان، العرض)
COLS = [('#', 34), ('اسم الأصل', 230), ('الفئة', 210), ('الكمية', 70), ('تكلفة الوحدة', 110), ('ضريبة %', 70),
        ('العمر (شهور)', 95), ('قيمة تخريدية', 105), ('الإجمالي', 120), ('', 46)]


class _AssetLine:
    def __init__(self, grid):
        self.grid = grid
        g = grid
        self.index = ft.Text('', size=12, color=theme.TEXT_MUTED, text_align=ft.TextAlign.CENTER)
        self.name = ft.TextField(width=COLS[1][1] - 6, border=ft.InputBorder.NONE, text_size=13, hint_text='اسم الأصل',
                                 content_padding=ft.Padding(left=6, right=6, top=6, bottom=6))
        self.name.on_change = self._touch
        self.name.on_submit = lambda e: g.open_category(self)
        self.category = theme.SearchableDropdown(label='فئة الأصل', width=COLS[2][1] - 6, options=g._cat_options, flat=True,
                                                 hint_text='دوس لاختيار الفئة', page=g.page)
        self.category.on_change = self._on_category
        self.qty = _num(COLS[3][1] - 6, value='1', on_change=self._recalc, on_submit=lambda e: g.focus(self.cost))
        self.cost = _num(COLS[4][1] - 6, on_change=self._recalc, on_submit=lambda e: g.next_line(self))
        self.tax = _num(COLS[5][1] - 6, value='15', on_change=self._recalc)
        self.life = _num(COLS[6][1] - 6, on_change=self._touch, hint='من الفئة')
        self.salvage = _num(COLS[7][1] - 6, on_change=self._touch, hint='من الفئة')
        self.total = ft.Text('', size=13, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
        self.remove_btn = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, icon_size=18, tooltip='حذف السطر',
                                        on_click=lambda e: g.remove_line(self))
        widgets = [self.index, self.name, self.category.control, self.qty, self.cost, self.tax, self.life, self.salvage, self.total, self.remove_btn]
        cells = [_cell(w, COLS[i][1]) for i, w in enumerate(widgets)]
        cells[0].content = ft.Container(content=self.index, alignment=ft.Alignment(0, 0))
        cells[8].content = ft.Container(content=self.total, alignment=ft.Alignment(0, 0))
        self.control = ft.Container(content=ft.Row(cells, spacing=0, vertical_alignment=ft.CrossAxisAlignment.START),
                                    border=ft.border.Border(bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT), right=ft.border.BorderSide(1, theme.BORDER_LIGHT)))

    def is_empty(self):
        return not ((self.name.value or '').strip() or self.category.value or (self.cost.value or '').strip()
                    or (self.life.value or '').strip() or (self.salvage.value or '').strip())

    def _touch(self, e=None):
        # أول ما السطر الأخير يتبدي، بنضيف سطر فاضي جاهز بعده
        if self is self.grid.lines[-1] and not self.is_empty():
            self.grid.add_line()
            self.grid.page.update()

    def _on_category(self, e=None):
        c = self.grid._cats.get(self.category.value or '')
        if c:
            self.life.hint_text = f'{c.useful_life_months}'
            self.salvage.hint_text = f'{c.salvage_percent:g}%'
            self.category.text_field.tooltip = (f'أصل {c.asset_account.code if c.asset_account else "-"} | مجمّع '
                                                f'{c.accumulated_depreciation_account.code if c.accumulated_depreciation_account else "-"} | مصروف '
                                                f'{c.depreciation_expense_account.code if c.depreciation_expense_account else "-"}')
        self._touch()
        self.grid.focus(self.qty)
        self.grid._changed()

    def calc(self):
        base = max(0, int(_to_float(self.qty.value))) * _to_float(self.cost.value)
        return base, base * _to_float(self.tax.value) / 100.0

    def _recalc(self, e=None):
        base, tax = self.calc()
        self.total.value = f'{base + tax:,.2f}' if base else ''
        self._touch()
        self.grid._changed()


class AssetLinesGrid:
    def __init__(self, page, on_change=None, rows_height=290):
        self.page = page
        self.on_change = on_change
        self._cats = {}
        self._cat_options = []
        self.lines = []
        header = ft.Container(
            content=ft.Row([_cell(ft.Text(t, size=12, weight=ft.FontWeight.BOLD), w, header=True) for t, w in COLS], spacing=0),
            bgcolor=theme.SURFACE_ALT, border=ft.border.Border(top=ft.border.BorderSide(1, theme.BORDER_LIGHT), bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT), right=ft.border.BorderSide(1, theme.BORDER_LIGHT)))
        self.rows_col = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, height=rows_height)
        self.add_btn = ft.OutlinedButton('إضافة سطر', icon=ft.Icons.ADD, on_click=lambda e: self.add_line(focus=True))
        self.control = ft.Column([header, self.rows_col, ft.Row([self.add_btn])], spacing=4)
        self.add_line()

    def set_categories(self, cats):
        self._cats = {str(c.id): c for c in cats}
        self._cat_options = [(str(c.id), c.name) for c in cats]
        for ln in self.lines:
            ln.category.options = self._cat_options

    def add_line(self, focus=False):
        ln = _AssetLine(self)
        self.lines.append(ln)
        self.rows_col.controls.append(ln.control)
        self._renumber()
        if focus:
            self.focus(ln.name)
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

    def focus_first(self):
        if self.lines:
            self.focus(self.lines[0].name)

    def open_category(self, line):
        """Enter بعد اسم الأصل = فتح اختيار الفئة."""
        line.category._open_picker()

    def next_line(self, line):
        """Enter بعد التكلفة = نروح لاسم الأصل في السطر اللي بعده (وبنضيف سطر لو ده آخر واحد)."""
        i = self.lines.index(line)
        if i + 1 < len(self.lines):
            self.focus(self.lines[i + 1].name)
        else:
            self.add_line(focus=True); self.page.update()

    def _changed(self):
        if self.on_change:
            self.on_change()

    # ---- ملخص حي ----
    def summary(self):
        units = subtotal = tax = 0.0
        for ln in self.lines:
            if ln.is_empty():
                continue
            base, t = ln.calc()
            units += max(0, int(_to_float(ln.qty.value))); subtotal += base; tax += t
        return int(units), subtotal, tax

    # ---- مسودة تلقائية ----
    def snapshot(self):
        """لقطة خام للسطور (من غير تحقق) للحفظ التلقائي كمسودة - بترجع بنفس شكل load_items."""
        return [{'name': ln.name.value or '', 'category': ln.category.value or '', 'qty': ln.qty.value or '', 'cost': ln.cost.value or '',
                 'tax': ln.tax.value or '', 'life': ln.life.value or '', 'salvage': ln.salvage.value or ''}
                for ln in self.lines if not ln.is_empty()]

    def load_items(self, items):
        """استرجاع سطور مسودة (الفئة اللي اتحذفت بتتساب فاضية)."""
        self._loading = True
        try:
            self.lines.clear(); self.rows_col.controls.clear()
            for it in items:
                ln = self.add_line()
                ln.name.value = it.get('name', ''); ln.qty.value = it.get('qty') or '1'; ln.cost.value = it.get('cost', '')
                ln.tax.value = it.get('tax') or '15'; ln.life.value = it.get('life', ''); ln.salvage.value = it.get('salvage', '')
                cat = it.get('category') or ''
                if cat in self._cats:
                    ln.category.value = cat
                    ln._on_category()
                ln._recalc()
            self.lines[:] = [l for l in self.lines if not l.is_empty()]
            self.rows_col.controls[:] = [l.control for l in self.lines]
            self.add_line()
            self._renumber(); self._changed()
        finally:
            self._loading = False

    # ---- للحفظ ----
    def get_items(self):
        """سطور الفاتورة بنفس شكل services.create_asset_purchase_invoice - بيرمي ValueError برقم السطر."""
        items = []
        for n, ln in enumerate(self.lines, 1):
            if ln.is_empty():
                continue
            name = (ln.name.value or '').strip()
            if not name:
                raise ValueError(f'السطر {n}: اكتب اسم الأصل')
            if not ln.category.value:
                raise ValueError(f'السطر {n}: اختار فئة الأصل')
            cost = _to_float(ln.cost.value)
            if cost <= 0:
                raise ValueError(f'السطر {n}: التكلفة يجب أن تكون أكبر من صفر')
            qty_f = _to_float(ln.qty.value, 1.0)
            if qty_f != int(qty_f):
                raise ValueError(f'السطر {n}: الكمية لازم تكون رقم صحيح')
            qty = int(qty_f)
            if qty < 1:
                raise ValueError(f'السطر {n}: الكمية يجب أن تكون 1 أو أكثر')
            if qty > services.MAX_ASSET_QTY_PER_LINE:
                raise ValueError(f'السطر {n}: الكمية أكبر من الحد المسموح ({services.MAX_ASSET_QTY_PER_LINE}) - قسّمها على أكتر من سطر')
            tax = _to_float(ln.tax.value)
            if tax < 0 or tax > 100:
                raise ValueError(f'السطر {n}: نسبة الضريبة غير صحيحة')
            life = None
            if (ln.life.value or '').strip():
                life = int(_to_float(ln.life.value))
                if life <= 0:
                    raise ValueError(f'السطر {n}: العمر الإنتاجي يجب أن يكون أكبر من صفر')
            salvage = None
            if (ln.salvage.value or '').strip():
                salvage = _to_float(ln.salvage.value)
                if salvage < 0 or salvage >= cost:
                    raise ValueError(f'السطر {n}: القيمة التخريدية يجب أن تكون أقل من التكلفة')
            c = self._cats[ln.category.value]
            items.append({'name': name, 'category_id': int(ln.category.value), 'category': c.name, 'cost': cost, 'quantity': qty,
                          'tax_rate': tax, 'salvage_value': salvage, 'useful_life_months': life, 'life_display': life or c.useful_life_months})
        return items
