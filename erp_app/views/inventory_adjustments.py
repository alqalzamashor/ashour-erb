import datetime
import os
import flet as ft
from ._approval import prompt as approval_prompt
from .. import services, theme
from ._doc_grid import doc_datetime, end_of_day


def build_inventory_adjustments(page: ft.Page):
    locations=services.list_locations(); branches=services.list_branches(True); allowed=services.user_branch_ids(); branches=[b for b in branches if not allowed or b.id in allowed]; centers=services.list_cost_centers(True); location=ft.Dropdown(label='المخزن',width=260,options=[ft.dropdown.Option(key=str(l.id),text=l.name) for l in locations],value=str(services.default_location_id()) if services.default_location_id() else None)
    branch=ft.Dropdown(label='الفرع',width=220,options=[ft.dropdown.Option(str(b.id),f'{b.code} - {b.name}') for b in branches],value=str(services.default_branch_id()) if services.default_branch_id() else None); center=ft.Dropdown(label='مركز التكلفة',width=220,options=[ft.dropdown.Option(str(c.id),f'{c.code} - {c.name}') for c in centers],value=str(services.default_cost_center_id()) if services.default_cost_center_id() else None)
    date_f=theme.DateField('تاريخ الجرد *', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
    asof_note=ft.Text('',size=12,color=theme.TEXT_MUTED)
    notes=ft.TextField(label='ملاحظات',width=400); rows_col=ft.Column(spacing=8,scroll=ft.ScrollMode.AUTO); err=ft.Text('',color=theme.DANGER,visible=False)
    history=ft.DataTable(columns=[ft.DataColumn(ft.Text('رقم التسوية')),ft.DataColumn(ft.Text('التاريخ')),ft.DataColumn(ft.Text('المخزن')),ft.DataColumn(ft.Text('عدد الفروق')),ft.DataColumn(ft.Text('قيمة الفرق')),ft.DataColumn(ft.Text('إجراءات'))],rows=[])

    # جرد الأصناف بترقيم صفحات وبحث: بدل ما نرسم صف + خانة كتابة لكل صنف (آلاف الأصناف = تهنيج)، بنعرض 50 صنف في الصفحة
    # والقيم اللي اتكتبت بتتحفظ في state['typed'] وبتفضل لما تتنقل بين الصفحات أو تبحث.
    state={'rows':[],'typed':{},'fields':[],'hidden':0}
    focus={'idx':None}
    hide_zero=ft.Switch(label='إخفاء الأصناف برصيد دفتري صفر',value=False)
    hidden_note=ft.Text('',size=12,color=theme.TEXT_MUTED)
    search=ft.TextField(label='بحث بالكود أو الاسم',width=260,prefix_icon=ft.Icons.SEARCH)
    pager=theme.PagerBar(lambda: render_page(),page,50)
    def filtered():
        q=(search.value or '').strip().lower()
        out=[r for r in state['rows'] if not q or q in r['product'].sku.lower() or q in r['product'].name.lower()]
        if hide_zero.value:
            # بنخفي اللي رصيده الدفتري صفر، إلا لو كتبت له عدد فعلي (عشان ما يختفيش من قدامك وإنت بتجرد زيادة)
            kept=[r for r in out if abs(r['balance'])>1e-9 or r['product'].id in state['typed']]
            state['hidden']=len(out)-len(kept)
            return kept
        state['hidden']=0
        return out
    def render_page(update=True):
        rows=filtered(); pager.set_total(len(rows),keep_page=True); a,b=pager.bounds(); out=[]; fields=[]
        hidden_note.value=f"مخفي {state['hidden']:,} صنف برصيد دفتري صفر" if hide_zero.value and state['hidden'] else ''
        for n,r in enumerate(rows[a:b]):
            p=r['product']
            def typed_change(ev,pid=p.id):
                state['typed'][pid]=ev.control.value
            f=ft.TextField(value=state['typed'].get(p.id,f"{r['balance']:g}"),width=150,keyboard_type=ft.KeyboardType.NUMBER,on_change=typed_change,
                           on_focus=lambda ev,i=n: focus.__setitem__('idx',i),on_submit=lambda ev,i=n: move(i+1))
            fields.append(f)
            out.append(ft.Row([ft.Text(p.sku,width=100),ft.Text(p.name,width=260),ft.Text(f"{r['balance']:g}",width=140),ft.Text(p.unit,width=100),f]))
        state['fields']=fields
        rows_col.controls=out or [ft.Text('مفيش أصناف مطابقة',color=theme.TEXT_MUTED)]
        if update: page.update()
    async def _focus(ctrl):
        try:
            await ctrl.focus()
        except Exception:
            pass
    def move(i):
        """السهم لتحت/لفوق (أو Enter): ينقل المؤشر لخانة الفعلي في الصنف اللي بعده/قبله. لو آخر صنف في الصفحة بيروح للصفحة اللي بعدها."""
        fields=state['fields']
        if not fields:
            return
        if i>=len(fields):
            if pager.page_no>=pager.pages():
                return
            pager.go(pager.page_no+1)            # بيعيد رسم الصفحة (render_page)
            i=0
        elif i<0:
            if pager.page_no<=1:
                return
            pager.go(pager.page_no-1)
            i=len(state['fields'])-1
        focus['idx']=i
        try:
            page.run_task(_focus,state['fields'][i])
        except Exception:
            pass
    def on_key(e):
        k=(getattr(e,'key','') or '').lower().replace(' ','')
        if focus['idx'] is None:
            return
        if k in ('arrowdown','down'):
            move(focus['idx']+1)
        elif k in ('arrowup','up'):
            move(focus['idx']-1)
    page.on_keyboard_event=on_key
    def on_search(e=None):
        pager.page_no=1; render_page()
    search.on_change=on_search
    def on_hide_zero(e=None):
        pager.page_no=1; render_page()
    hide_zero.on_change=on_hide_zero
    def asof():
        """الرصيد الدفتري في تاريخ الجرد = رصيد المخزن لحد نهاية اليوم ده (كل الحركات اللي قبله وفيه)."""
        try:
            return end_of_day(date_f.value)
        except Exception:
            return None
    def on_date_change(e=None):
        # تغيير التاريخ: الرصيد الدفتري بيتحسب تاني للتاريخ الجديد، والأرقام اللي كتبتها بتفضل
        a=asof()
        if a is None: return
        state['rows']=services.get_stock_balance_report(location_id=int(location.value), as_of=a) if location.value else []
        asof_note.value=f"الرصيد الدفتري = رصيد المخزن حتى نهاية يوم {a:%d/%m/%Y}"
        render_page()
    def load_count(e=None):
        state['rows']=[]; state['typed']={}; search.value=''
        if location.value:
            state['rows']=services.get_stock_balance_report(location_id=int(location.value), as_of=asof())
        asof_note.value=f"الرصيد الدفتري = رصيد المخزن حتى نهاية يوم {asof():%d/%m/%Y}" if asof() else ''
        pager.page_no=1; render_page(update=False)
        try: page.update()
        except Exception: pass
    def export_adjustment(adj_id, kind):
        try:
            from ..report_export import export_pdf, export_excel
            d = services.get_inventory_adjustment_detail(adj_id)
            sub = f"{d['number']} - {d['date']:%d/%m/%Y} - {d['location']}" + (f" - {d['notes']}" if d['notes'] else '')
            data = {'adjustment': d, 'date_from': None, 'date_to': None, 'title_suffix': sub}
            out_dir = os.path.join(services.APP_DIR, 'exports'); os.makedirs(out_dir, exist_ok=True)
            theme.open_or_download_file(page, (export_pdf if kind == 'pdf' else export_excel)(data, 'inventory_adjustment', out_dir))
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر الإنشاء: {ex}'), open=True)); page.update()

    def open_preview(adj_id):
        """معاينة التسوية: بيانات السند + ملخص الزيادة والعجز + جدول الفروق (بالترتيب والترقيم)، مع طباعة PDF وتصدير Excel."""
        try:
            d = services.get_inventory_adjustment_detail(adj_id)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, data='error')); page.update(); return
        def info(label, value):
            return ft.Container(bgcolor=theme.PRIMARY_LIGHT, border_radius=8, padding=ft.Padding(left=10, right=10, top=6, bottom=6),
                                content=ft.Column([ft.Text(label, size=11, color=theme.TEXT_MUTED), ft.Text(str(value), weight=ft.FontWeight.BOLD, size=13)], spacing=0, tight=True))
        def card(label, value, color, sub):
            return theme.stat_card(label, value, color, sub, padding=12)
        def row_builder(l):
            diff = l['difference']; color = theme.SUCCESS if diff > 0 else theme.DANGER
            return ft.DataRow(cells=[ft.DataCell(ft.Text(l['sku'])), ft.DataCell(ft.Text(l['name'])), ft.DataCell(ft.Text(l['unit'])), ft.DataCell(ft.Text(f"{l['theoretical']:g}")),
                                     ft.DataCell(ft.Text(f"{l['counted']:g}")), ft.DataCell(ft.Text(f"{'+' if diff > 0 else ''}{diff:g}", color=color, weight=ft.FontWeight.BOLD)),
                                     ft.DataCell(ft.Text(f"{l['unit_cost']:,.2f}")), ft.DataCell(ft.Text(f"{l['value']:,.2f}", color=color)),
                                     ft.DataCell(ft.Text('زيادة' if diff > 0 else 'عجز', color=color, weight=ft.FontWeight.BOLD, size=12))])
        tbl = theme.SortableDataTable(columns=[('الكود', lambda l: l['sku']), ('الصنف', lambda l: l['name']), ('الوحدة', None), ('الرصيد الدفتري', lambda l: l['theoretical'], True), ('الرصيد الفعلي', lambda l: l['counted'], True),
                                               ('الفرق', lambda l: l['difference'], True), ('تكلفة الوحدة', lambda l: l['unit_cost'], True), ('قيمة الفرق', lambda l: l['value'], True), ('النوع', lambda l: l['difference'])],
                                      row_builder=row_builder, page=page, page_size=50, column_spacing=18, horizontal_margin=10)
        tbl.set_data(d['lines'])
        head = [info('رقم السند', d['number']), info('التاريخ', f"{d['date']:%Y-%m-%d}"), info('المخزن', d['location']), info('الفرع', d['branch']), info('مركز التكلفة', d['cost_center']), info('القيد المحاسبي', d['journal_number'])]
        cards = [card('زيادة جرد', f"{d['surplus_value']:,.2f}", theme.SUCCESS, f"{d['surplus_count']} صنف"), card('عجز جرد', f"{d['shortage_value']:,.2f}", theme.DANGER, f"{d['shortage_count']} صنف"),
                 card('صافي قيمة الفرق', f"{d['net_value']:,.2f}", theme.PRIMARY_TEXT, 'زيادة - عجز')]
        body = [ft.Row(head, wrap=True, spacing=8), *([ft.Text(f"ملاحظات: {d['notes']}", size=12, color=theme.TEXT_MUTED)] if d['notes'] else []), ft.Row(cards, wrap=True, spacing=10),
                ft.Text('الفروق المسجّلة في التسوية (الأصناف المطابقة للرصيد الدفتري ما بتتسجّلش)', size=12, color=theme.TEXT_MUTED), theme.h_scroll(tbl.control)]
        dlg = ft.AlertDialog(modal=True, title=ft.Text(f"معاينة التسوية الجردية {d['number']}"), content=ft.Container(width=980, content=ft.Column(body, spacing=10, scroll=ft.ScrollMode.AUTO, height=600)),
                             actions=[ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export_adjustment(adj_id, 'excel')),
                                      ft.FilledButton('طباعة PDF', icon=ft.Icons.PRINT_OUTLINED, bgcolor=theme.PRIMARY, on_click=lambda e: export_adjustment(adj_id, 'pdf')),
                                      ft.TextButton('إغلاق', on_click=lambda e: (setattr(dlg, 'open', False), page.update()))])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def refresh_history():
        hs=[]
        for a in services.list_inventory_adjustments()[:200]:
            val=sum(abs(x.difference_qty*x.unit_cost) for x in a.lines)
            hs.append(ft.DataRow(cells=[ft.DataCell(ft.Text(a.number)),ft.DataCell(ft.Text(a.date.strftime('%Y-%m-%d'))),ft.DataCell(ft.Text(a.location.name)),ft.DataCell(ft.Text(str(len(a.lines)))),ft.DataCell(ft.Text(f'{val:,.2f}')),
                ft.DataCell(ft.Row([ft.TextButton('معاينة',icon=ft.Icons.VISIBILITY_OUTLINED,on_click=lambda e,i=a.id: open_preview(i)),
                                    ft.IconButton(icon=ft.Icons.PRINT_OUTLINED,tooltip='طباعة PDF',icon_color=theme.PRIMARY,on_click=lambda e,i=a.id: export_adjustment(i,'pdf'))],spacing=0))]))
        history.rows=hs; page.update()
    def save(e):
        try:
            counts={}
            for r in state['rows']:
                pid=r['product'].id; raw=state['typed'].get(pid,f"{r['balance']:g}")
                try: counts[pid]=float(str(raw).replace(',','').strip() or 0)
                except ValueError: raise ValueError(f"قيمة الجرد للصنف {r['product'].sku} غير صحيحة: {raw}")
            services.create_inventory_adjustment(int(location.value),counts,notes.value or '',branch_id=int(branch.value) if branch.value else None,cost_center_id=int(center.value) if center.value else None,adjustment_date=doc_datetime(date_f.value, end_of_day=True))
            err.visible=False; notes.value=''; load_count(); refresh_history()
            page.overlay.append(ft.SnackBar(ft.Text('تم اعتماد التسوية الجردية وتحديث المخزون والقيد المحاسبي'), open=True)); page.update()
        except Exception as ex: err.value=str(ex); err.visible=True; page.update(); approval_prompt(page, ex)
    location.on_change=load_count; date_f.on_change=on_date_change; load_count(); refresh_history()
    header_row=ft.Row([ft.Text('الكود',width=100,weight=ft.FontWeight.BOLD),ft.Text('الصنف',width=260,weight=ft.FontWeight.BOLD),ft.Text('الدفتري في التاريخ',width=140,weight=ft.FontWeight.BOLD),ft.Text('الوحدة',width=100,weight=ft.FontWeight.BOLD),ft.Text('الفعلي',width=150,weight=ft.FontWeight.BOLD)])
    return ft.Column([theme.page_title('التسويات الجردية','الجرد الدفتري مقابل الفعلي وتسجيل الفرق آلياً'),ft.Container(height=10),theme.card(ft.Column([ft.Row([date_f.control,location,branch,center,notes,theme.guard_submit(ft.FilledButton('اعتماد الجرد',icon=ft.Icons.CHECK_CIRCLE_OUTLINE,bgcolor=theme.PRIMARY,on_click=save))],wrap=True),err,asof_note,ft.Row([search,hide_zero,hidden_note],wrap=True,spacing=16),header_row,ft.Container(content=rows_col,height=360),pager.control]) ),ft.Container(height=14),theme.card(ft.Column([ft.Text('سجل التسويات',size=17,weight=ft.FontWeight.BOLD),theme.h_scroll(history)]),expand=True)],expand=True,scroll=ft.ScrollMode.AUTO)
