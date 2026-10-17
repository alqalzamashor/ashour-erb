import datetime
import flet as ft
from .. import services, theme, attendance


def build_attendance(page: ft.Page):
    """الحضور والانصراف: بصمات الجهاز، الأجهزة، ربط الموظفين بأرقام الجهاز، العطلات والراحة الأسبوعية."""
    tabs = theme.SimpleTabs(page)

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def refresh_all():
        tabs.set_tabs([('البصمات', logs_tab()), ('الأجهزة', devices_tab()), ('ربط الموظفين', link_tab()), ('العطلات والراحة', holidays_tab())],
                      selected_index=tabs.selected_index)
        page.update()

    # ---------------------------------------------------------------- البصمات
    def logs_tab():
        today = datetime.date.today()
        from_f = theme.DateField('من', page, width=160, value=today.replace(day=1).strftime('%Y-%m-%d'))
        to_f = theme.DateField('إلى', page, width=160, value=today.strftime('%Y-%m-%d'))
        holder = ft.Container()
        info = ft.Text('', color=theme.TEXT_MUTED)

        def load(e=None):
            try:
                d1 = datetime.datetime.strptime(from_f.value, '%Y-%m-%d').date(); d2 = datetime.datetime.strptime(to_f.value, '%Y-%m-%d').date()
                rows = attendance.daily_summary(d1, d2, limit=500)
            except Exception as ex:
                return snack(str(ex))
            holder.content = ft.Column([ft.DataTable(
                columns=[ft.DataColumn(ft.Text(x)) for x in ['الموظف', 'اليوم', 'أول بصمة', 'آخر بصمة', 'عدد البصمات']],
                rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(r['name'])), ft.DataCell(ft.Text(r['date'].strftime('%Y-%m-%d'))),
                                        ft.DataCell(ft.Text(r['first'].strftime('%H:%M'))), ft.DataCell(ft.Text(r['last'].strftime('%H:%M'))),
                                        ft.DataCell(ft.Text(str(r['count'])))]) for r in rows])], scroll=ft.ScrollMode.AUTO, height=420)
            info.value = f'{len(rows)} يوم حضور' + (' (أول 500)' if len(rows) >= 500 else '')
            page.update()

        async def do_import(e):
            path = await theme.pick_file(page, 'اختر ملف البصمات', ['csv', 'xlsx', 'txt', 'dat'])
            if not path:
                return
            try:
                r = attendance.import_file(path)
                msg = f"اتستورد {r['inserted']} بصمة ({r['duplicates']} مكررة اتجاهلت)"
                if r['unmatched']:
                    msg += f" - أرقام مش مربوطة بموظفين: {'، '.join(r['unmatched'][:8])}"
                snack(msg); load()
            except Exception as ex:
                snack(str(ex))

        load()
        return ft.Column([
            ft.Row([from_f.control, to_f.control, ft.OutlinedButton('عرض', icon=ft.Icons.SEARCH, on_click=load),
                    ft.FilledButton('استيراد ملف بصمات', icon=ft.Icons.UPLOAD_FILE, bgcolor=theme.PRIMARY, on_click=do_import)], wrap=True),
            ft.Text('الملف: CSV أو Excel فيه عمود رقم الموظف (على الجهاز) وعمود تاريخ ووقت (أو تاريخ ووقت منفصلين).', size=12, color=theme.TEXT_MUTED),
            info, holder], spacing=10)

    # ---------------------------------------------------------------- الأجهزة
    def devices_tab():
        serial_f = ft.TextField(label='السيريال نمبر *', width=200)
        name_f = ft.TextField(label='اسم الجهاز', width=180)
        host_f = ft.TextField(label='IP الجهاز (للسحب المباشر)', width=200)
        port_f = ft.TextField(label='البورت', width=90, value='4370')
        en_cb = ft.Checkbox(label='مفعّل', value=True)
        err = ft.Text('', color=theme.DANGER, visible=False)
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الجهاز', 'السيريال', 'الحالة', 'آخر اتصال', 'بصمات مستلمة', '']], rows=[])

        def add(e):
            try:
                attendance.save_device(serial_f.value, name_f.value, host_f.value, port_f.value, en_cb.value)
                refresh_all()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        def toggle(d):
            attendance.save_device(d.serial, d.name, d.host, d.port, not d.enabled, device_id=d.id); refresh_all()

        def pull(d):
            try:
                r = attendance.pull_device(d.id)
                snack(f"اتسحب {r['inserted']} بصمة جديدة"); refresh_all()
            except Exception as ex:
                snack(str(ex))

        def remove(d):
            attendance.delete_device(d.id); refresh_all()

        for d in attendance.list_devices():
            table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(d.name or '-')), ft.DataCell(ft.Text(d.serial)),
                ft.DataCell(ft.Text('مفعّل' if d.enabled else 'بانتظار الموافقة', color=theme.SUCCESS if d.enabled else theme.WARNING)),
                ft.DataCell(ft.Text(d.last_seen.strftime('%Y-%m-%d %H:%M') if d.last_seen else '-')),
                ft.DataCell(ft.Text(str(d.last_count or 0))),
                ft.DataCell(ft.Row([ft.TextButton('تفعيل/إيقاف', on_click=lambda e, d=d: toggle(d)),
                                    ft.TextButton('سحب الآن', on_click=lambda e, d=d: pull(d)),
                                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, on_click=lambda e, d=d: remove(d))], spacing=0))]))
        return ft.Column([
            ft.Text('إعداد الجهاز (ADMS): في قائمة الاتصال/Cloud Server بالجهاز اكتب عنوان السيرفر ده وبورته الداخلي (ERP_INTERNAL_PORT، الافتراضي 8600). '
                    'الجهاز الجديد بيظهر هنا "بانتظار الموافقة" - فعّله عشان بصماته تتسجّل.', size=12, color=theme.TEXT_MUTED),
            ft.Row([serial_f, name_f, host_f, port_f, en_cb, ft.FilledButton('إضافة جهاز', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=add)], wrap=True),
            err, ft.Column([table], scroll=ft.ScrollMode.AUTO)], spacing=10)

    # ---------------------------------------------------------------- ربط الموظفين
    def link_tab():
        rows, fields = [], {}
        for e in services.list_employees():
            tf = ft.TextField(value=e.device_user_id or '', width=140, dense=True)
            fields[e.id] = tf
            rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(e.code or '')), ft.DataCell(ft.Text(e.name)), ft.DataCell(tf)]))
        err = ft.Text('', color=theme.DANGER, visible=False)

        def save(ev):
            errs = []
            for eid, tf in fields.items():
                try:
                    attendance.set_employee_device_id(eid, tf.value)
                except Exception as ex:
                    errs.append(str(ex))
            if errs:
                err.value = ' | '.join(errs[:3]); err.visible = True; page.update()
            else:
                snack('تم حفظ الأرقام'); refresh_all()

        return ft.Column([
            ft.Text('اكتب رقم كل موظف زي ما هو متسجل على جهاز البصمة (User ID).', size=12, color=theme.TEXT_MUTED),
            ft.FilledButton('حفظ', icon=ft.Icons.SAVE, bgcolor=theme.PRIMARY, on_click=save), err,
            ft.Column([ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الكود', 'الموظف', 'رقم الجهاز']], rows=rows)], scroll=ft.ScrollMode.AUTO, height=460)], spacing=10)

    # ---------------------------------------------------------------- العطلات
    def holidays_tab():
        off = attendance.get_weekly_off()
        cbs = {wd: ft.Checkbox(label=nm, value=wd in off) for wd, nm in attendance.WEEKDAY_NAMES.items()}
        d_f = theme.DateField('تاريخ العطلة', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
        n_f = ft.TextField(label='الاسم (اختياري)', width=220)
        err = ft.Text('', color=theme.DANGER, visible=False)

        def save_off(e):
            try:
                attendance.set_weekly_off([wd for wd, c in cbs.items() if c.value]); snack('تم حفظ الراحة الأسبوعية')
            except Exception as ex:
                snack(str(ex))

        def add(e):
            try:
                attendance.add_holiday(datetime.datetime.strptime(d_f.value, '%Y-%m-%d').date(), n_f.value)
                refresh_all()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        def remove(h):
            attendance.delete_holiday(h.id); refresh_all()

        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['التاريخ', 'الاسم', '']], rows=[
            ft.DataRow(cells=[ft.DataCell(ft.Text(h.date.strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(h.name or '-')),
                              ft.DataCell(ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, on_click=lambda e, h=h: remove(h)))])
            for h in attendance.list_holidays(datetime.date.today().year)])
        return ft.Column([
            ft.Text('الراحة الأسبوعية (مش بتتحسب غياب):', weight=ft.FontWeight.BOLD),
            ft.Row(list(cbs.values()), wrap=True), ft.OutlinedButton('حفظ الراحة', on_click=save_off),
            ft.Divider(), ft.Text('العطلات الرسمية:', weight=ft.FontWeight.BOLD),
            ft.Row([d_f.control, n_f, ft.FilledButton('إضافة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=add)], wrap=True), err, table], spacing=10)

    theme.call_without_page_update(page, refresh_all)
    return ft.Column([theme.page_title('الحضور والبصمة', 'بصمات الجهاز وربطها بالغياب في الرواتب'),
                      ft.Container(height=10), tabs.control], expand=True)
