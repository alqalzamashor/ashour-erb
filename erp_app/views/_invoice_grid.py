import flet as ft
from .. import services, theme

# (العنوان، العرض) - مجموعها ~1010 بكسل
COLS = [('#', 34), ('الصنف', 300), ('الوحدة', 120), ('الكمية', 90), ('السعر', 110), ('الخصم', 100), ('ضريبة %', 80), ('الإجمالي', 130), ('', 46)]


def _cell(content, width, header=False):
    return ft.Container(
        content=content, width=width, alignment=ft.Alignment(0, 0) if header else None,
        padding=ft.Padding(left=2, right=2, top=1, bottom=1),
        border=ft.border.Border(left=ft.border.BorderSide(1, theme.BORDER_LIGHT)),
    )


def _num(width, value='', on_change=None, on_submit=None, hint=None):
    f = ft.TextField(
        value=value, width=width, text_align=ft.TextAlign.CENTER, keyboard_type=ft.KeyboardType.NUMBER,
        border=ft.InputBorder.NONE, content_padding=ft.Padding(left=4, right=4, top=6, bottom=6), text_size=13, hint_text=hint,
    )
    f.on_change = on_change
    f.on_submit = on_submit
    return f


def _to_float(text, default=0.0):
    try:
        return float(str(text).replace(',', '').strip()) if str(text).strip() else default
    except ValueError:
        return default


class BatchRow:
    """صف إضافي تحت سطر الشراء/الاستلام للأصناف المتتبَّعة: تاريخ الصلاحية (لو الصنف له صلاحية) + رقم التشغيلة (اختياري).
    بيظهر تلقائي لما تختار صنف متتبَّع، وبيتعبّى تاريخ الصلاحية من مدة الصلاحية الافتراضية للصنف لو معرّفة."""

    def __init__(self):
        self.expiry = ft.TextField(label='تاريخ الصلاحية *', width=170, dense=True, text_size=13, hint_text='يوم/شهر/سنة', content_padding=ft.Padding(left=8, right=8, top=6, bottom=6))
        self.batch = ft.TextField(label='رقم التشغيلة (اختياري)', width=200, dense=True, text_size=13, content_padding=ft.Padding(left=8, right=8, top=6, bottom=6))
        self.hint = ft.Text('', size=11.5, color=theme.TEXT_MUTED)
        self.track_expiry = False
        self.control = ft.Container(visible=False, padding=ft.Padding(left=40, right=8, top=0, bottom=4), bgcolor='#F8FCFA',
                                    content=ft.Row([ft.Icon(ft.Icons.EVENT_AVAILABLE_OUTLINED, size=16, color=theme.PRIMARY), self.expiry, self.batch, self.hint], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER))

    def apply_product(self, p, tracked):
        """بيظهر/يخفي الصف حسب الصنف. tracked = الصنف متتبَّع (طريقة إخراج أو صلاحية)."""
        self.control.visible = bool(tracked)
        self.track_expiry = bool(tracked and getattr(p, 'track_expiry', False))
        self.expiry.visible = self.track_expiry
        if tracked:
            import datetime
            if self.track_expiry and not (self.expiry.value or '').strip() and getattr(p, 'shelf_life_days', None):
                self.expiry.value = (datetime.date.today() + datetime.timedelta(days=int(p.shelf_life_days))).strftime('%d/%m/%Y')
            method = {'fifo': 'FIFO', 'lifo': 'LIFO', 'fefo': 'الأقرب انتهاءً'}.get(getattr(p, 'issue_method', None) or 'none', 'الأقرب انتهاءً')
            self.hint.value = f'طريقة الإخراج: {method}'

    def values(self, n):
        """(expiry_datetime أو None, batch_no) - بيرمي ValueError برقم السطر لو التاريخ ناقص/غلط."""
        if not self.control.visible:
            return None, None
        import datetime
        exp = None
        if self.track_expiry:
            txt = (self.expiry.value or '').strip()
            d = theme.parse_date_text(txt) if txt else None
            if txt and not d:
                raise ValueError(f'السطر {n}: تاريخ الصلاحية غير صحيح (اكتبه يوم/شهر/سنة)')
            if not d:
                raise ValueError(f'السطر {n}: حدد تاريخ الصلاحية للصنف')
            exp = datetime.datetime.combine(d, datetime.time(0, 0))
        return exp, (self.batch.value or '').strip() or None


class _Line:
    def __init__(self, grid):
        self.grid = grid
        self.unit_lines = {}
        g = grid
        self.index = ft.Text('', size=12, color=theme.TEXT_MUTED, text_align=ft.TextAlign.CENTER)
        self.product = theme.SearchableDropdown(label='الصنف', width=COLS[1][1] - 6, options=g._options, flat=True,
                                                hint_text='اكتب كود أو اسم الصنف ثم Enter', suggestions_height=180, page=g.page)
        self.product.on_change = self._on_product
        self.product.on_submit = self._after_product_submit
        self.unit = ft.Dropdown(width=COLS[2][1] - 6, options=[], border=ft.InputBorder.NONE,
                                content_padding=ft.Padding(left=4, right=4, top=6, bottom=6), text_size=13)
        self.unit.on_change = self._on_unit
        self.qty = _num(COLS[3][1] - 6, on_change=self._recalc, on_submit=lambda e: g.focus(self.price))
        self.price = _num(COLS[4][1] - 6, on_change=self._recalc, on_submit=lambda e: g.focus(self.disc))
        self.disc = _num(COLS[5][1] - 6, on_change=self._recalc, on_submit=self._from_discount)
        self.tax = _num(COLS[6][1] - 6, on_change=self._recalc)
        self.total = ft.Text('', size=13, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
        self.remove_btn = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, icon_size=18, tooltip='حذف السطر',
                                        on_click=lambda e: g.remove_line(self))
        widgets = [self.index, self.product.control, self.unit, self.qty, self.price, self.disc, self.tax, self.total, self.remove_btn]
        cells = [_cell(w, COLS[i][1]) for i, w in enumerate(widgets)]
        cells[0].content = ft.Container(content=self.index, alignment=ft.Alignment(0, 0))
        cells[7].content = ft.Container(content=self.total, alignment=ft.Alignment(0, 0))
        self.batch_row = BatchRow()
        self.control = ft.Container(content=ft.Column([ft.Row(cells, spacing=0, vertical_alignment=ft.CrossAxisAlignment.START), self.batch_row.control], spacing=0),
                                    border=ft.border.Border(bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT), right=ft.border.BorderSide(1, theme.BORDER_LIGHT)))

    # ---- أحداث ----
    def _on_product(self, e=None):
        g = self.grid
        p = g._products.get(self.product.value or '')
        if not p:
            return
        lines = services.list_product_units(p.id)
        self.unit_lines = {str(x.unit_id): x for x in lines}
        self.unit.options = [ft.dropdown.Option(str(x.unit_id), x.unit.name) for x in lines]
        default = next((x for x in lines if x.is_default), lines[0] if lines else None)
        self.unit.value = str(default.unit_id) if default else None
        self._set_auto_price(p, default)
        self.batch_row.apply_product(p, (not g.is_sales) and services.is_batch_tracked(p))      # صلاحية/تشغيلة في الشراء بس (البيع بيتوزّع تلقائي)
        self.tax.value = f'{p.tax_rate:g}'
        if not (self.qty.value or '').strip():
            self.qty.value = '1'
        if not (self.disc.value or '').strip():
            self.disc.value = '0'
        self._recalc()
        if self is g.lines[-1]:
            g.add_line()           # دايمًا فيه سطر فاضي جاهز في الآخر
        g.focus(self.qty)

    def _set_auto_price(self, p, unit_line):
        """السعر التلقائي للصنف: لو الشبكة ليها محدد أسعار (فواتير المبيعات: قائمة أسعار
        العميل) بنستخدمه، وإلا سعر الوحدة أو السعر الافتراضي للصنف."""
        g = self.grid
        from_list = False
        if g.price_resolver:
            price, from_list = g.price_resolver(p, unit_line)
        else:
            price = (unit_line.sale_price if g.is_sales else unit_line.cost_price) if unit_line else None
            if price is None:
                price = p.sale_price if g.is_sales else p.cost_price
        price = price or 0
        self.price.value = f'{price:g}'
        self._auto_price = float(price)
        self.price.color = theme.PRIMARY if from_list else None
        self.price.tooltip = 'سعر خاص من قائمة أسعار العميل' if from_list else None

    def reprice(self):
        """إعادة تسعير السطر (لما العميل يتغيّر): بنغيّر السعر بس لو المستخدم ما عدّلوش يدويًا."""
        if not self.product.value:
            return
        p = self.grid._products.get(self.product.value)
        if not p:
            return
        current = _to_float(self.price.value)
        if getattr(self, '_auto_price', None) is not None and abs(current - self._auto_price) > 1e-9:
            return            # المستخدم عدّل السعر بنفسه - منلمسوش
        self._set_auto_price(p, self.unit_lines.get(self.unit.value or ''))
        self._recalc()

    def _after_product_submit(self, e=None):
        if self.product.value:
            self.grid.focus(self.qty)

    def _on_unit(self, e=None):
        if not self.product.value:
            return
        x = self.unit_lines.get(self.unit.value or '')
        p = self.grid._products.get(self.product.value or '')
        if x and p and self.grid.price_resolver:
            self._set_auto_price(p, x)
        elif x:
            val = x.sale_price if self.grid.is_sales else x.cost_price
            if val is not None:
                self.price.value = f'{val:g}'
                self._auto_price = float(val)
        self._recalc()

    def _from_discount(self, e=None):
        g = self.grid
        i = g.lines.index(self)
        if i + 1 < len(g.lines):
            g.focus(g.lines[i + 1].product)
        else:
            g.add_line(focus=True)

    def calc(self):
        qty, price, disc, tax = (_to_float(self.qty.value), _to_float(self.price.value), _to_float(self.disc.value), _to_float(self.tax.value))
        base = max(0.0, qty * price - disc)
        return base, base * tax / 100.0

    def _recalc(self, e=None):
        if self.product.value:
            base, tax = self.calc()
            self.total.value = f'{base + tax:,.2f}'
        else:
            self.total.value = ''
        self.grid._changed()


class InvoiceLinesGrid:
    """جدول سطور الفاتورة (شكل Excel): كل سطر = صنف + وحدة + كمية + سعر + خصم + ضريبة + إجمالي.
    - بيتضاف سطر فاضي تلقائيًا أول ما تختار صنف في آخر سطر.
    - Enter: الصنف ← الكمية ← السعر ← الخصم ← الصنف في السطر اللي بعده (وآخر سطر بيتضاف له سطر جديد).
    - الوحدة والضريبة بالماوس/Tab. السطور الفاضية (من غير صنف) بتتجاهل عند الحفظ."""

    def __init__(self, page, is_sales=False, on_change=None, rows_height=290):
        self.page = page
        self.is_sales = is_sales
        self.on_change = on_change
        self.price_resolver = None     # دالة (صنف، سطر وحدة) -> (سعر، من قائمة أسعار؟) - بتتحدد من شاشة المبيعات
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

    # ---- الأصناف ----
    def set_products(self, products):
        self._products = {str(p.id): p for p in products}
        self._options = [(str(p.id), f'{p.sku} - {p.name}') for p in products]
        for ln in self.lines:
            ln.product.options = self._options

    # ---- السطور ----
    def add_line(self, focus=False):
        ln = _Line(self)
        self.lines.append(ln)
        self.rows_col.controls.append(ln.control)
        self._renumber()
        if focus:
            self.focus(ln.product)
            self._scroll_end()
        return ln

    def remove_line(self, line):
        if line in self.lines:
            self.lines.remove(line)
            self.rows_col.controls.remove(line.control)
        if not self.lines:
            self.add_line()
        self._renumber()
        self._changed()

    def load_items(self, items):
        """تحميل بنود محفوظة (للتعديل): كل بند dict فيه product_id, unit_id, quantity, unit_price, discount, tax_rate.
        الأسعار المحمّلة بتفضل زي ما هي (مش بتتعاد تسعيرها لما العميل يتغيّر)."""
        self.lines.clear(); self.rows_col.controls.clear()
        for it in items:
            ln = self.add_line()
            pid = str(it['product_id'])
            ln.product.value = pid
            unit_lines = services.list_product_units(int(pid))
            ln.unit_lines = {str(x.unit_id): x for x in unit_lines}
            ln.unit.options = [ft.dropdown.Option(str(x.unit_id), x.unit.name) for x in unit_lines]
            uid = str(it['unit_id']) if it.get('unit_id') else None
            ln.unit.value = uid if uid in ln.unit_lines else (str(unit_lines[0].unit_id) if unit_lines else None)
            ln.qty.value = f"{float(it['quantity']):g}"; ln.price.value = f"{float(it['unit_price']):g}"
            ln.disc.value = f"{float(it.get('discount', 0) or 0):g}"; ln.tax.value = f"{float(it.get('tax_rate', 15)):g}"
            ln._auto_price = -1.0          # علامة: السعر محفوظ - متتعادش تسعيره تلقائيًا
            ln._recalc()
        self.add_line()
        self._renumber()
        self._changed()

    def snapshot(self):
        """لقطة خام لسطور الجدول (من غير تحقق) للحفظ التلقائي كمسودة - بترجع بنفس شكل load_items."""
        out = []
        for ln in self.lines:
            if ln.product.value:
                out.append({'product_id': ln.product.value, 'unit_id': ln.unit.value or None, 'quantity': _to_float(ln.qty.value, 1.0),
                            'unit_price': _to_float(ln.price.value), 'discount': _to_float(ln.disc.value), 'tax_rate': _to_float(ln.tax.value)})
        return out

    def reprice(self):
        """بيعيد تسعير كل السطور (بعد تغيير العميل) من غير ما يلمس الأسعار المعدّلة يدويًا."""
        for ln in self.lines:
            ln.reprice()
        self._changed()

    def clear(self):
        self.lines.clear()
        self.rows_col.controls.clear()
        self.add_line()
        self._changed()

    def _renumber(self):
        for i, ln in enumerate(self.lines):
            ln.index.value = str(i + 1)
            ln.control.bgcolor = theme.ROW_BG[i % 2]

    # ---- تركيز ----
    async def _focus(self, ctrl):
        try:
            await ctrl.focus()
        except Exception:
            pass

    def focus(self, ctrl):
        target = getattr(ctrl, 'text_field', None) or getattr(getattr(ctrl, 'product', None), 'text_field', None) or ctrl
        try:
            self.page.run_task(self._focus, target)
        except Exception:
            pass

    def focus_first(self):
        if self.lines:
            self.focus(self.lines[0].product)

    async def _scroll_to_end(self):
        try:
            await self.rows_col.scroll_to(offset=-1, duration=150)
        except Exception:
            pass

    def _scroll_end(self):
        try:
            self.page.run_task(self._scroll_to_end)
        except Exception:
            pass

    # ---- حسابات ----
    def _changed(self):
        if self.on_change:
            self.on_change()

    def preview_items(self):
        """قيم تقريبية للإجماليات الحية (بتتجاهل الأخطاء ومش بترفع استثناء)."""
        out = []
        for ln in self.lines:
            if ln.product.value:
                out.append({'quantity': _to_float(ln.qty.value), 'unit_price': _to_float(ln.price.value),
                            'discount': _to_float(ln.disc.value), 'tax_rate': _to_float(ln.tax.value)})
        return out

    def get_items(self):
        """سطور الفاتورة للحفظ - بيرمي ValueError برقم السطر لو فيه قيمة غلط."""
        items = []
        for n, ln in enumerate(self.lines, 1):
            if not ln.product.value:
                continue
            def num(field, label, minimum=0.0, strict_positive=False):
                txt = (field.value or '').strip()
                try:
                    v = float(txt.replace(',', '')) if txt else 0.0
                except ValueError:
                    raise ValueError(f'السطر {n}: {label} غير صحيحة')
                if (strict_positive and v <= 0) or v < minimum:
                    raise ValueError(f'السطر {n}: {label} ' + ('يجب أن تكون أكبر من صفر' if strict_positive else 'لا يمكن أن تكون سالبة'))
                return v
            qty = num(ln.qty, 'الكمية', strict_positive=True)
            price = num(ln.price, 'السعر')
            disc = num(ln.disc, 'الخصم')
            tax = num(ln.tax, 'نسبة الضريبة')
            if disc > qty * price:
                raise ValueError(f'السطر {n}: الخصم أكبر من قيمة السطر')
            p = self._products[ln.product.value]
            unit_id = int(ln.unit.value) if ln.unit.value else None
            unit_line = ln.unit_lines.get(ln.unit.value or '')
            exp, batch_no = ln.batch_row.values(n)
            items.append({'product_id': int(ln.product.value), 'unit_id': unit_id,
                          'unit_name': unit_line.unit.name if unit_line else p.unit,
                          'quantity': qty, 'unit_price': price, 'discount': disc, 'tax_rate': tax, 'expiry_date': exp, 'batch_no': batch_no})
        return items
