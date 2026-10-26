"""عارض التقارير الموحّد (الجيل الجديد) - واجهة فوق report_engine:
  • طريقة العرض والتجميع بالاختيار (قايمة خيارات: تفصيلي / مجمّع حسب أي عمود / شهري / سنوي / ملخص + خيارات خاصة بكل تقرير) وتجميع متعدد حتى 3 مستويات
  • فرز بالضغط على أي عنوان، فلترة لكل عمود (>100 ، 10..50 ، !كلمة ، a|b ، تواريخ) وبحث عام، شرائح الفلاتر الشغّالة
  • اختيار وترتيب الأعمدة وإعادة الضبط، وحفظ اختيارات المستخدم لكل تقرير
  • إجماليات حية (تتغيّر مع الفلاتر) + كروت KPI + رسم بياني حسب التجميع
  • تصدير Excel/PDF بنفس العرض الحالي بالظبط (الأعمدة والفلاتر والفرز والتجميع)
الاستخدام:
    v = ReportViewer(page, 'ledger', 'دفتر الأستاذ', [Col('date','التاريخ',DATE), Col('debit','مدين',MONEY,'sum'), ...])
    v.set_rows([{...}, ...]);  layout = ft.Column([..., v.control])"""
import json
import os

import flet as ft

from . import report_engine as E
from . import services, theme
from .report_engine import Col, ViewState          # noqa: F401  (للاستيراد من الشاشات)

PAGE_SIZE = 100
LEVEL_BG = ['#E6F2EC', '#EEF6F2', '#F5FAF7']


class Mode:
    """خيار طريقة عرض: مجموعة تجميع/فرز جاهزة."""

    def __init__(self, key, label, group_keys=(), sort_key=None, asc=True, summary_only=False):
        self.key, self.label, self.group_keys = key, label, list(group_keys)
        self.sort_key, self.asc, self.summary_only = sort_key, asc, summary_only


# ----------------------------------------------------------------- حفظ تفضيلات المستخدم لكل تقرير
def _prefs_path():
    from . import db
    return os.path.join(db.APP_DIR, 'report_prefs.json')


def _pref_key(report_id):
    try:
        u = services._get_user()
        name = (u.get('username') if isinstance(u, dict) else getattr(u, 'username', '')) or ''
    except Exception:      # noqa: BLE001
        name = ''
    return f'{name}:{report_id}'


def load_prefs(report_id):
    try:
        with open(_prefs_path(), encoding='utf-8') as f:
            return json.load(f).get(_pref_key(report_id), {})
    except Exception:      # noqa: BLE001
        return {}


def save_prefs(report_id, prefs):
    try:
        path = _prefs_path()
        try:
            with open(path, encoding='utf-8') as f:
                allp = json.load(f)
        except Exception:      # noqa: BLE001
            allp = {}
        allp[_pref_key(report_id)] = prefs
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(allp, f, ensure_ascii=False)
    except Exception:      # noqa: BLE001 - التفضيلات مش لازم تعطّل التقرير
        pass


# ----------------------------------------------------------------- العارض
class ReportViewer:
    def __init__(self, page, report_id, title, columns, modes=None, kpis='auto', on_row_click=None, show_export=True,
                 default_mode='detail', page_size=PAGE_SIZE, chart_value=None, subtitle='', empty_text='لا توجد بيانات في الفترة/الفلاتر دي'):
        self.page, self.report_id, self.title, self.subtitle = page, report_id, title, subtitle
        self.cols = list(columns)
        self.by = {c.key: c for c in self.cols}
        self.kpis_spec, self.on_row_click, self.chart_value, self.empty_text = kpis, on_row_click, chart_value, empty_text
        self.rows = []
        self.expanded = set()
        self.modes = self._build_modes(modes or [])
        self.mode_key = default_mode
        self.state = ViewState(visible=[c.key for c in self.cols if c.visible])
        self.show_chart = False
        self.show_filters_dialog = None
        self._res = None
        self._load_prefs()

        # ---- أدوات الأعلى
        self.mode_dd = ft.Dropdown(label='طريقة العرض والتجميع', width=250, dense=True,
                                   options=[ft.dropdown.Option(m.key, m.label) for m in self.modes] + [ft.dropdown.Option('custom', 'مخصّص')], value=self.mode_key)
        self.mode_dd.on_select = self._on_mode
        gopts = [ft.dropdown.Option('', 'بدون')] + [ft.dropdown.Option(k, l) for k, l in self._group_choices()]
        self.level_dds = []
        for i in range(3):
            dd = ft.Dropdown(label=f'تجميع {i + 1}' if i else 'تجميع حسب', width=190, dense=True, options=list(gopts), value='')
            dd.on_select = lambda e, i=i: self._on_level(i)
            self.level_dds.append(dd)
        self.search = ft.TextField(label='بحث في كل الأعمدة', width=240, dense=True, prefix_icon=ft.Icons.SEARCH, border_radius=10, on_change=self._on_search)
        self.btn_cols = ft.OutlinedButton('الأعمدة', icon=ft.Icons.VIEW_COLUMN_OUTLINED, on_click=self._open_columns)
        self.btn_filters = ft.OutlinedButton('فلاتر', icon=ft.Icons.FILTER_ALT_OUTLINED, on_click=self._open_filters)
        self.btn_chart = ft.OutlinedButton('رسم', icon=ft.Icons.BAR_CHART, on_click=self._toggle_chart)
        self.btn_open = ft.TextButton('فتح الكل', icon=ft.Icons.UNFOLD_MORE, on_click=lambda e: self._set_all(True), visible=False)
        self.btn_close = ft.TextButton('قفل الكل', icon=ft.Icons.UNFOLD_LESS, on_click=lambda e: self._set_all(False), visible=False)
        self.btn_reset = ft.TextButton('إعادة ضبط', icon=ft.Icons.RESTART_ALT, on_click=self._reset)
        exp = []
        if show_export:
            exp = [ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: self.export('xlsx')),
                   ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: self.export('pdf'))]
        self.chips = ft.Row([], wrap=True, spacing=6, run_spacing=4)
        self.kpi_row = ft.Row([], wrap=True, spacing=12, visible=False)
        self.chart_box = ft.Container(visible=False)
        self.info = ft.Text('', size=12, color=theme.TEXT_MUTED)
        self.totals = ft.Row([], wrap=True, spacing=8, run_spacing=6)
        self.empty = theme.empty_state(self.empty_text)
        self.empty.visible = False

        self.table = ft.DataTable(columns=[ft.DataColumn(ft.Text(self.by[k].label), numeric=self.by[k].numeric) for k in self.state.visible], rows=[], heading_row_height=44, data_row_min_height=36, column_spacing=22)
        self.pager = theme.RowPager(self.table, page, page_size)
        toolbar = theme.card(ft.Column([
            ft.Row([self.mode_dd] + self.level_dds, wrap=True, spacing=10, run_spacing=8),
            ft.Row([self.search, self.btn_cols, self.btn_filters, self.btn_chart, self.btn_open, self.btn_close, self.btn_reset, ft.Container(expand=True)] + exp, wrap=True, spacing=8, run_spacing=8),
            self.chips,
        ], spacing=8), padding=14)
        self.control = ft.Column([self.kpi_row, toolbar, self.chart_box, theme.card(ft.Column([self.info, self.empty, theme.h_scroll(self.table), self.totals], spacing=8), padding=12, expand=True)],
                                 spacing=10)
        self._apply_mode(self.mode_key, from_pref=True)

    # ------------------------------------------------------------- إعداد الأوضاع والتفضيلات
    def _group_choices(self):
        out = []
        for c in self.cols:
            if not c.groupable:
                continue
            out.append((c.key, c.label))
            if c.kind == E.DATE:
                out += [(f'{c.key}:month', f'{c.label} (شهر)'), (f'{c.key}:year', f'{c.label} (سنة)')]
        return out

    def _build_modes(self, extra):
        modes = [Mode('detail', 'تفصيلي (كل الصفوف)')] + list(extra)
        have = {m.key for m in modes}
        for k, l in self._group_choices():
            if f'by:{k}' not in have:
                modes.append(Mode(f'by:{k}', f'مجمّع حسب {l}', [k]))
        first = next((k for k, _ in self._group_choices()), None)
        if first and 'summary' not in have:
            modes.append(Mode('summary', f'ملخص فقط حسب {self.by[first.split(":")[0]].label}', [first], summary_only=True))
        return modes

    def _load_prefs(self):
        p = load_prefs(self.report_id)
        vis = [k for k in p.get('visible', []) if k in self.by]
        if vis:
            vis += [c.key for c in self.cols if c.key not in vis and c.visible and c.key not in p.get('hidden', [])]
            self.state.visible = vis
        if p.get('mode') and any(m.key == p['mode'] for m in self.modes) or p.get('mode') == 'custom':
            self.mode_key = p['mode']
        self._pref_groups = [g for g in p.get('groups', []) if g.split(':')[0] in self.by]

    def _save_prefs(self):
        hidden = [c.key for c in self.cols if c.key not in self.state.visible]
        save_prefs(self.report_id, {'visible': self.state.visible, 'hidden': hidden, 'mode': self.mode_key, 'groups': self.state.group_keys})

    def _apply_mode(self, key, from_pref=False):
        self.mode_key = key
        self.mode_dd.value = key
        if key == 'custom':
            gks = (self._pref_groups if from_pref else self.state.group_keys) or []
            self.state.group_keys, self.state.summary_only = list(gks), False
        else:
            m = next((m for m in self.modes if m.key == key), self.modes[0])
            self.state.group_keys, self.state.summary_only = list(m.group_keys), m.summary_only
            if m.sort_key:
                self.state.sort_key, self.state.asc = m.sort_key, m.asc
        for i, dd in enumerate(self.level_dds):
            dd.value = self.state.group_keys[i] if i < len(self.state.group_keys) else ''
        self.expanded = set()

    # ------------------------------------------------------------- أحداث
    def _refresh_ui(self, keep_page=False):
        self._render(keep_page)
        try:
            self.page.update()
        except Exception:      # noqa: BLE001
            pass

    def _on_mode(self, e=None):
        self._apply_mode(self.mode_dd.value or 'detail')
        self._save_prefs(); self._refresh_ui()

    def _on_level(self, i):
        gks = [dd.value for dd in self.level_dds if dd.value]
        seen = []
        for g in gks:                                  # مفيش تكرار لنفس العمود في مستويين
            if g not in seen:
                seen.append(g)
        self.state.group_keys, self.state.summary_only = seen, False
        self.mode_key = 'custom'; self.mode_dd.value = 'custom'
        self.expanded = set()
        self._save_prefs(); self._refresh_ui()

    def _on_search(self, e=None):
        self.state.search = self.search.value or ''
        self._refresh_ui()

    def _toggle_chart(self, e=None):
        self.show_chart = not self.show_chart
        self._refresh_ui(True)

    def _set_all(self, open_):
        self.expanded = E.all_group_ids(self._res['nodes']) if open_ else set()
        self._refresh_ui()

    def _toggle_group(self, gid):
        self.expanded.discard(gid) if gid in self.expanded else self.expanded.add(gid)
        self._refresh_ui(True)

    def _sort(self, key):
        if self.state.sort_key == key:
            self.state.asc = not self.state.asc
        else:
            self.state.sort_key, self.state.asc = key, True
        self._refresh_ui()

    def _reset(self, e=None):
        self.state = ViewState(visible=[c.key for c in self.cols if c.visible])
        self.search.value = ''
        self._apply_mode('detail')
        self._save_prefs(); self._refresh_ui()

    # ------------------------------------------------------------- نوافذ الأعمدة والفلاتر
    def _open_columns(self, e=None):
        order = list(self.state.visible) + [c.key for c in self.cols if c.key not in self.state.visible]
        rows_col = ft.Column([], spacing=0, tight=True, scroll=ft.ScrollMode.AUTO, height=360)

        def build():
            rows_col.controls = []
            for i, k in enumerate(order):
                c = self.by[k]
                cb = ft.Checkbox(label=c.label, value=k in self.state.visible, on_change=lambda ev, k=k: toggle(k, ev.control.value))
                up = ft.IconButton(ft.Icons.ARROW_UPWARD, icon_size=18, tooltip='أعلى', disabled=i == 0, on_click=lambda ev, i=i: move(i, -1))
                dn = ft.IconButton(ft.Icons.ARROW_DOWNWARD, icon_size=18, tooltip='أسفل', disabled=i == len(order) - 1, on_click=lambda ev, i=i: move(i, 1))
                rows_col.controls.append(ft.Row([cb, ft.Container(expand=True), up, dn]))

        def toggle(k, on):
            vis = [x for x in order if (x in self.state.visible and x != k) or (x == k and on)]
            self.state.visible = vis or [order[0]]

        def move(i, d):
            order[i], order[i + d] = order[i + d], order[i]
            self.state.visible = [x for x in order if x in self.state.visible]
            build(); self.page.update()

        def done(ev=None):
            dlg.open = False
            self.state.visible = [x for x in order if x in self.state.visible]
            self._save_prefs(); self._refresh_ui()

        def all_on(ev):
            self.state.visible = list(order); build(); self.page.update()
        build()
        dlg = ft.AlertDialog(modal=True, title=ft.Text('اختيار وترتيب الأعمدة'), content=ft.Container(rows_col, width=360),
                             actions=[ft.TextButton('إظهار الكل', on_click=all_on), ft.FilledButton('تطبيق', on_click=done)])
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    def _open_filters(self, e=None):
        fields = {}
        hints = {E.MONEY: 'مثال: >100 أو 10..50', E.QTY: 'مثال: >0 أو ..5', E.INT: 'مثال: >=2', E.PCT: 'مثال: >10', E.DATE: 'مثال: 2026-03 أو >=2026-01-01 أو a..b', E.TEXT: 'كلمة أو a|b أو !كلمة أو =مطابق'}
        for c in self.cols:
            fields[c.key] = ft.TextField(label=c.label, value=self.state.filters.get(c.key, ''), hint_text=hints.get(c.kind, ''), dense=True, border_radius=10)

        def apply(ev=None):
            self.state.filters = {k: f.value.strip() for k, f in fields.items() if (f.value or '').strip()}
            dlg.open = False; self._refresh_ui()

        def clear(ev):
            for f in fields.values():
                f.value = ''
            self.page.update()
        dlg = ft.AlertDialog(modal=True, title=ft.Text('فلترة الأعمدة'),
                             content=ft.Container(ft.Column(list(fields.values()), spacing=8, tight=True, scroll=ft.ScrollMode.AUTO, height=420), width=380),
                             actions=[ft.TextButton('مسح الكل', on_click=clear), ft.TextButton('إلغاء', on_click=lambda ev: (setattr(dlg, 'open', False), self.page.update())),
                                      ft.FilledButton('تطبيق', on_click=apply)])
        self.page.overlay.append(dlg); dlg.open = True; self.page.update()

    # ------------------------------------------------------------- البيانات
    def set_rows(self, rows, keep_page=False):
        self.rows = list(rows)
        self.expanded &= E.all_group_ids(E.build_groups(self.rows, self.cols, self.state.group_keys)) if self.state.group_keys else set()
        self._render(keep_page)

    def refresh(self):
        self._refresh_ui()

    def view_table(self):
        return E.export_table(self.rows, self.cols, self.state)

    def export(self, fmt):
        try:
            from .report_export import export_excel, export_pdf
            data = dict(self.view_table(), title=self.title)
            theme.open_or_download_file(self.page, (export_excel if fmt == 'xlsx' else export_pdf)(data, 'report_view', services.downloads_dir()))
        except Exception as ex:      # noqa: BLE001
            theme.notify(self.page, f'تعذر التصدير: {ex}', 'error')

    # ------------------------------------------------------------- الرسم
    def _render(self, keep_page=False):
        st = self.state
        res = self._res = E.run(self.rows, self.cols, st)
        vis = res['visible_cols']
        grouped = bool(res['nodes'])
        # الأعمدة (العنوان بيفرز كل الداتا مش الصفحة بس)
        dcols = []
        for c in vis:
            def on_sort(e, k=c.key):
                self._sort(k)
            dcols.append(ft.DataColumn(ft.Text(c.label, weight=ft.FontWeight.BOLD), numeric=c.numeric, on_sort=on_sort))
        self.table.columns = dcols
        idx = next((i for i, c in enumerate(vis) if c.key == st.sort_key), None)
        self.table.sort_column_index, self.table.sort_ascending = idx, st.asc
        # الصفوف
        if grouped:
            items = E.flatten(res['nodes'], self.expanded, st.summary_only)
        else:
            items = [('row', r, 0) for r in res['rows']]
        self.pager.set_items(items, lambda it: self._build_row(it, vis), keep_page=keep_page)
        # أدوات تعتمد على الحالة
        self.btn_open.visible = self.btn_close.visible = grouped
        self.empty.visible = not items
        self.btn_filters.content = ft.Text('فلاتر' + (f' ({len(st.filters)})' if st.filters else ''))
        self.btn_filters.icon = ft.Icons.FILTER_ALT if st.filters else ft.Icons.FILTER_ALT_OUTLINED
        self.btn_chart.icon = ft.Icons.BAR_CHART if not self.show_chart else ft.Icons.CLOSE
        self._render_chips()
        self._render_totals(res, vis)
        self._render_kpis(res)
        self._render_chart()
        n, src = res['count'], res['source_count']
        self.info.value = f'{n:,} صف' + (f' من أصل {src:,} (بعد الفلاتر)' if n != src else '') + (f' • مجمّع إلى {len(res["nodes"]):,} مجموعة' if grouped else '')

    def _build_row(self, item, vis):
        if item[0] == 'group':
            n = item[1]
            opened = n.id in self.expanded
            bg = LEVEL_BG[min(n.level, 2)]
            can_open = bool(n.children) or not self.state.summary_only
            lead = ft.IconButton(ft.Icons.EXPAND_MORE if opened else ft.Icons.CHEVRON_LEFT, icon_size=18, width=28, height=28, padding=0,
                                 on_click=lambda e, g=n.id: self._toggle_group(g)) if can_open else ft.Container(width=28)
            cells = []
            for i, c in enumerate(vis):
                if i == 0:
                    cells.append(ft.DataCell(ft.Row([ft.Container(width=16 * n.level), lead, ft.Text(f'{n.label}', weight=ft.FontWeight.BOLD), ft.Text(f'({n.count})', size=11, color=theme.TEXT_MUTED)], spacing=2),
                                             on_tap=lambda e, g=n.id: self._toggle_group(g)))
                elif c.numeric and n.agg.get(c.key) is not None:
                    cells.append(ft.DataCell(ft.Text(E.fmt(n.agg[c.key], c), weight=ft.FontWeight.BOLD)))
                else:
                    cells.append(ft.DataCell(ft.Text('')))
            return ft.DataRow(color=bg, cells=cells)
        r, level = item[1], item[2]
        style = r.get('_style')
        bold = ft.FontWeight.BOLD if style in ('section', 'bold') else None
        color = theme.DANGER if style == 'warn' else None
        cells = []
        for i, c in enumerate(vis):
            txt = ft.Text(E.fmt(r.get(c.key), c), weight=bold or (ft.FontWeight.BOLD if c.bold else None), color=color)
            if i == 0 and level:
                cell_content = ft.Row([ft.Container(width=16 * level + 28), txt], spacing=2)
            else:
                cell_content = txt
            tap = (lambda e, row=r: self.on_row_click(row)) if self.on_row_click and i < 2 else None
            cells.append(ft.DataCell(cell_content, on_tap=tap))
        return ft.DataRow(color='#FEF3C7' if style == 'net' else (theme.MAIN_ROW_BG if style == 'section' else None), cells=cells)

    def _render_chips(self):
        st = self.state
        chips = []

        def chip(text, on_close):
            return ft.Container(ft.Row([ft.Text(text, size=12), ft.IconButton(ft.Icons.CLOSE, icon_size=14, width=24, height=24, padding=0, on_click=on_close, tooltip='إزالة')], spacing=2, tight=True),
                                bgcolor=theme.PRIMARY_LIGHT, border_radius=14, padding=ft.Padding(left=10, right=4, top=0, bottom=0))
        for k, t in st.filters.items():
            chips.append(chip(f'{self.by[k].label}: {t}', lambda e, k=k: (st.filters.pop(k, None), self._refresh_ui())))
        if (st.search or '').strip():
            chips.append(chip(f'بحث: {st.search}', lambda e: (setattr(self.search, 'value', ''), setattr(st, 'search', ''), self._refresh_ui())))
        self.chips.controls = chips
        self.chips.visible = bool(chips)

    def _render_totals(self, res, vis):
        t = res['totals']
        items = [ft.Container(ft.Row([ft.Text(c.label, size=11, color=theme.TEXT_MUTED), ft.Text(E.fmt(t[c.key], c), size=13, weight=ft.FontWeight.BOLD, color=theme.DANGER if (t[c.key] or 0) < -0.004 and c.kind == E.MONEY else None)], spacing=6, tight=True),
                              bgcolor='#FEF3C7', border_radius=8, padding=ft.Padding(left=10, right=10, top=4, bottom=4))
                 for c in vis if c.numeric and t.get(c.key) is not None]
        self.totals.controls = ([ft.Text('الإجمالي:', size=12, weight=ft.FontWeight.BOLD)] + items) if items else []

    def _render_kpis(self, res):
        spec = self.kpis_spec
        if not spec:
            self.kpi_row.visible = False
            return
        pairs = E.auto_kpis(res['rows'] if not self.state.group_keys else [r for n in res['nodes'] for r in n.rows], self.cols) if spec == 'auto' else [(l, f(res)) for l, f in spec]
        self.kpi_row.controls = [ft.Container(theme.card(ft.Column([ft.Text(l, size=11, color=theme.TEXT_MUTED), ft.Text(str(v), size=19, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)], spacing=2, tight=True), padding=14), width=215)
                                 for l, v in pairs]
        self.kpi_row.visible = True

    def _render_chart(self):
        self.chart_box.visible = self.show_chart
        if not self.show_chart:
            return
        data = E.chart_data(self.rows, self.cols, self.state, self.chart_value)
        if not data or not data[1]:
            self.chart_box.content = theme.empty_state('مفيش بيانات للرسم', hint='اختار تجميع أو غيّر الفلاتر')
            return
        title, pts = data
        top = max((abs(v) for _, v in pts), default=0) or 1
        vertical = len(pts) > 3 and self.state.group_keys and self.state.group_keys[0].endswith((':month', ':year'))
        num = self.by.get(self.chart_value) or next((c for c in self.cols if c.numeric and c.total == 'sum'), None) or next((c for c in self.cols if c.numeric), self.cols[0])
        if vertical:
            bars = ft.Row([ft.Column([ft.Text(E.fmt(v, num), size=10),
                                      ft.Container(width=34, height=max(3, int(150 * abs(v) / top)), bgcolor=theme.DANGER if v < 0 else theme.PRIMARY, border_radius=4),
                                      ft.Text(lbl, size=10, color=theme.TEXT_MUTED)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=3, alignment=ft.MainAxisAlignment.END)
                           for lbl, v in pts], spacing=10, scroll=ft.ScrollMode.AUTO, vertical_alignment=ft.CrossAxisAlignment.END, height=210)
            body = bars
        else:
            body = ft.Column([ft.Row([ft.Container(ft.Text(lbl, size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS), width=170),
                                      ft.Container(ft.Container(bgcolor=theme.DANGER if v < 0 else theme.PRIMARY, border_radius=4, height=14, width=max(3, int(320 * abs(v) / top))), expand=True),
                                      ft.Text(E.fmt(v, num), size=12, weight=ft.FontWeight.BOLD, width=110)], spacing=8) for lbl, v in pts], spacing=6)
        self.chart_box.content = theme.card(ft.Column([ft.Text(title, size=14, weight=ft.FontWeight.BOLD), body], spacing=10), padding=14)


# ----------------------------------------------------------------- مساعد: أي قايمة dicts => عارض جاهز (بيستنتج نوع كل عمود)
import datetime as _dt
import re as _re

_NUM_RE = _re.compile(r'^-?\d[\d,]*(\.\d+)?$')
_DATE_RE = _re.compile(r'^\d{4}-\d{2}-\d{2}')


def _as_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and _NUM_RE.match(v.strip()):
        return float(v.replace(',', '').strip())
    return None


def infer_columns(rows, keys, labels, last_keys=(), no_sum_words=('price', 'cost', 'rate', 'سعر', 'تكلفة', 'avg', 'متوسط')):
    """أعمدة Col من البيانات نفسها: رقمي لو كل القيم الغير فاضية أرقام (حتى لو نصوص منسّقة "1,234.50")، تاريخ لو date/'YYYY-MM-DD'.
    الإجمالي: مجموع، أو "آخر قيمة" للأرصدة، أو من غير إجمالي للأسعار والتكاليف."""
    cols = []
    for k, label in zip(keys, labels):
        vals = [r.get(k) for r in rows if r.get(k) not in (None, '')]
        kind, total = E.TEXT, None
        if vals and all(_as_number(v) is not None for v in vals):
            lk = (k + ' ' + label).lower()
            kind = E.QTY if any(w in lk for w in ('qty', 'quantity', 'count', 'كمية', 'عدد')) else E.PCT if any(w in lk for w in ('pct', 'percent', '%', 'نسبة')) else E.MONEY
            total = 'last' if (k in last_keys or 'balance' in lk or 'رصيد' in lk) else None if any(w in lk for w in no_sum_words) or kind == E.PCT else 'sum'
        elif vals and all(isinstance(v, (_dt.date, _dt.datetime)) or (isinstance(v, str) and _DATE_RE.match(v)) for v in vals):
            kind = E.DATE
        cols.append(Col(k, label, kind, total))
    return cols


def normalize_rows(rows, cols):
    out = []
    for r in rows:
        n = dict(r)
        for c in cols:
            v = r.get(c.key)
            if c.numeric:
                n[c.key] = _as_number(v)
            elif c.kind == E.DATE and isinstance(v, str):
                try:
                    n[c.key] = _dt.date.fromisoformat(v[:10])
                except ValueError:
                    pass
        if r.get('_bold'):
            n['_style'] = n.get('_style') or 'bold'
        out.append(n)
    return out


def table_viewer(page, report_id, title, rows, keys, labels, **kw):
    """عارض جاهز من قايمة dicts: v = table_viewer(page, 'sales_x', 'عنوان', rows, ['date','total'], ['التاريخ','الإجمالي']); layout.append(v.control)"""
    cols = infer_columns(rows, keys, labels, last_keys=kw.pop('last_keys', ()))
    v = ReportViewer(page, report_id, title, cols, **kw)
    v.set_rows(normalize_rows(rows, cols))
    return v


def smart_table(page, report_id, rows, keys, heads, title='', min_rows=12, **kw):
    """للشاشات اللي فيها دالة جدول محلية: لو الصفوف كتيرة (> min_rows) بترجّع العارض الجديد (فرز/فلترة/تجميع/أعمدة/رسم/تصدير)،
    وإلا جدول بسيط زي زمان (الجداول الصغيرة مش محتاجة شريط أدوات)."""
    rows = list(rows)
    if len(rows) > min_rows:
        return table_viewer(page, report_id, title or ' / '.join(heads[:2]), rows, keys, heads, kpis=kw.pop('kpis', None), **kw).control
    return theme.h_scroll(ft.DataTable(columns=[ft.DataColumn(ft.Text(h)) for h in heads],
                                       rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(str(r.get(k, '')))) for k in keys]) for r in rows], heading_row_height=38))
