import datetime
import flet as ft
from .. import services, theme, attendance


def build_attendance(page: ft.Page):
    """الحضور والانصراف: بصمات الجهاز، الأجهزة، ربط الموظفين بأرقام الجهاز، العطلات والراحة الأسبوعية."""
    tabs = theme.SimpleTabs(page)

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def refresh_all():
        tabs.set_tabs([('البصمات', logs_tab()), ('الأجهزة', devices_tab()), ('ربط الموظفين', link_tab()), ('العطلات والراحة', holidays_tab()), ('قواعد الدوام', shift_tab()), ('الورديات', shifts_tab())],
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
                columns=[ft.DataColumn(ft.Text(x)) for x in ['الموظف', 'اليوم', 'أول بصمة', 'آخر بصمة', 'عدد البصمات', 'تأخير (د)', 'خروج مبكر (د)', 'إضافي (د)', 'الوردية']],
                rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(r['name'])), ft.DataCell(ft.Text(r['date'].strftime('%Y-%m-%d'))),
                                        ft.DataCell(ft.Text(r['first'].strftime('%H:%M'))), ft.DataCell(ft.Text(r['last'].strftime('%H:%M'))),
                                        ft.DataCell(ft.Text(str(r['count']))),
                                        ft.DataCell(ft.Text(str(r['late']) if r['late'] else '-', color=theme.DANGER if r['late'] else None)),
                                        ft.DataCell(ft.Text(str(r['early']) if r['early'] else '-', color=theme.WARNING if r['early'] else None)),
                                        ft.DataCell(ft.Text(str(r['overtime']) if r['overtime'] else '-', color=theme.SUCCESS if r['overtime'] else None)),
                                        ft.DataCell(ft.Text(r.get('shift') or 'الافتراضي', size=12))]) for r in rows])], scroll=ft.ScrollMode.AUTO, height=420)
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
        rows, fields, shift_fields, current_shift = [], {}, {}, {}
        eff_f = theme.DateField('سريان تغيير الوردية من (فاضي: من النهارده)', page, width=300)
        shift_opts = [ft.dropdown.Option('', 'دوام الشركة الافتراضي')] + [ft.dropdown.Option(str(x.id), x.name) for x in attendance.list_shifts(active_only=True)]
        for e in services.list_employees():
            tf = ft.TextField(value=e.device_user_id or '', width=140, dense=True)
            fields[e.id] = tf
            cur_sid = str(e.shift_id) if getattr(e, 'shift_id', None) else ''
            sd = ft.Dropdown(options=shift_opts, value=cur_sid, width=220, dense=True)
            shift_fields[e.id] = sd
            current_shift[e.id] = cur_sid
            hist = attendance.list_shift_history(e.id)
            hist_txt = ' ← '.join((f'{n} (من {d:%Y-%m-%d})' if d else f'{n} (الأصل)') for d, n in hist) if hist else '-'
            rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(e.code or '')), ft.DataCell(ft.Text(e.name)), ft.DataCell(tf), ft.DataCell(sd),
                                          ft.DataCell(ft.Text(hist_txt, size=11, color=theme.TEXT_MUTED))]))
        err = ft.Text('', color=theme.DANGER, visible=False)

        def save(ev):
            errs = []
            for eid, tf in fields.items():
                try:
                    attendance.set_employee_device_id(eid, tf.value)
                    if (shift_fields[eid].value or '') != current_shift[eid]:         # بنغيّر بس اللي اتغيّر عشان ميتسجلش تاريخ ربط لكل الموظفين
                        attendance.set_employee_shift(eid, int(shift_fields[eid].value) if shift_fields[eid].value else None, eff_f.value or None)
                except Exception as ex:
                    errs.append(str(ex))
            if errs:
                err.value = ' | '.join(errs[:3]); err.visible = True; page.update()
            else:
                snack('تم حفظ الأرقام'); refresh_all()

        return ft.Column([
            ft.Text('اكتب رقم كل موظف زي ما هو متسجل على جهاز البصمة (User ID)، واختار وردية الموظف (أو سيبها على دوام الشركة). '
                    'تغيير الوردية بيسري من التاريخ اللي تحدده (الأيام قبله تفضل على الوردية القديمة)؛ ولو أول مرة تربط الموظف وسيبت التاريخ فاضي بتنطبق على كل البصمات.', size=12, color=theme.TEXT_MUTED),
            ft.Row([eff_f.control, ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save)], wrap=True), err,
            ft.Column([ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الكود', 'الموظف', 'رقم الجهاز', 'الوردية', 'تاريخ الورديات']], rows=rows)], scroll=ft.ScrollMode.AUTO, height=460)], spacing=10)

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

    # ---------------------------------------------------------------- قواعد الدوام (تأخير / إضافي)
    def shift_tab():
        r = attendance.get_shift_rules()
        st = ft.TextField(label='بداية الدوام (HH:MM)', width=170, value=r['start_txt'])
        en = ft.TextField(label='نهاية الدوام (HH:MM)', width=170, value=r['end_txt'])
        grace = ft.TextField(label='سماحية التأخير (دقائق)', width=170, value=str(r['grace']), keyboard_type=ft.KeyboardType.NUMBER)
        late_cb = ft.Checkbox(label='خصم التأخير والخروج المبكر من الراتب', value=r['late_on'])
        ot_cb = ft.Checkbox(label='احتساب الإضافي وإضافته على الراتب', value=r['ot_on'])
        ot_min = ft.TextField(label='أقل مدة إضافي (دقائق)', width=170, value=str(r['ot_min']), keyboard_type=ft.KeyboardType.NUMBER)
        ot_mult = ft.TextField(label='معامل الساعة الإضافية', width=170, value=f"{r['ot_mult']:g}", keyboard_type=ft.KeyboardType.NUMBER)
        err = ft.Text('', color=theme.DANGER, visible=False)

        def save(e):
            try:
                attendance.set_shift_rules(st.value, en.value, grace.value, late_cb.value, ot_cb.value, ot_min.value, ot_mult.value)
                err.visible = False; snack('تم حفظ قواعد الدوام'); refresh_all()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        return ft.Column([
            ft.Text('دوام موحّد للشركة. التأخير = وقت أول بصمة بعد (البداية + السماحية) محسوب من بداية الدوام. الخروج المبكر والإضافي بيحتاجوا بصمتين في اليوم. '
                    'يوم الراحة أو العطلة: كل مدة التواجد إضافي. الحساب بيتم من زرار "احسب الغياب والتأخير والإضافي من البصمة" في شاشة الرواتب (دورة مسودة).',
                    size=12, color=theme.TEXT_MUTED),
            ft.Row([st, en, grace], wrap=True), late_cb, ft.Row([ot_cb, ot_min, ot_mult], wrap=True),
            ft.Text('أجر دقيقة التأخير = أجر اليوم ÷ دقائق الدوام. أجر ساعة الإضافي = الراتب الأساسي ÷ (أساس اليوم × ساعات الدوام) × المعامل.', size=12, color=theme.TEXT_MUTED),
            ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save), err], spacing=10)

    # ---------------------------------------------------------------- الورديات
    def shifts_tab():
        name_f = ft.TextField(label='اسم الوردية *', width=200)
        st_f = ft.TextField(label='البداية (HH:MM)', width=140, value='08:00')
        en_f = ft.TextField(label='النهاية (HH:MM)', width=140, value='16:00')
        gr_f = ft.TextField(label='سماحية (دقائق) - فاضي للشركة', width=230, keyboard_type=ft.KeyboardType.NUMBER)
        own_off = ft.Checkbox(label='راحة أسبوعية خاصة بالوردية', value=False)
        cbs = {wd: ft.Checkbox(label=nm, value=wd in attendance.get_weekly_off(), disabled=True) for wd, nm in attendance.WEEKDAY_NAMES.items()}
        editing = {'id': None}
        err = ft.Text('', color=theme.DANGER, visible=False)
        days_row = ft.Row(list(cbs.values()), scroll=ft.ScrollMode.AUTO, spacing=14, visible=False)

        def on_own(e=None):
            for c in cbs.values():
                c.disabled = not own_off.value
            days_row.visible = bool(own_off.value)
            page.update()
        own_off.on_change = on_own

        def clear(e=None):
            editing['id'] = None; name_f.value = ''; st_f.value = '08:00'; en_f.value = '16:00'; gr_f.value = ''; own_off.value = False
            off = attendance.get_weekly_off()
            for wd, c in cbs.items():
                c.value = wd in off; c.disabled = True
            days_row.visible = False
            save_btn.text = 'إضافة وردية'; page.update()

        def save(e):
            try:
                attendance.save_shift(name_f.value, st_f.value, en_f.value, gr_f.value,
                                      [wd for wd, c in cbs.items() if c.value] if own_off.value else None, True, editing['id'])
                err.visible = False; snack('تم حفظ الوردية'); refresh_all()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        def edit(sh):
            editing['id'] = sh.id; name_f.value = sh.name; st_f.value = sh.start_time; en_f.value = sh.end_time
            gr_f.value = '' if sh.grace_minutes is None else str(sh.grace_minutes)
            has_off = sh.weekly_off_days is not None and str(sh.weekly_off_days).strip() != ''
            own_off.value = has_off
            offs = attendance._parse_days(sh.weekly_off_days) if has_off else attendance.get_weekly_off()
            for wd, c in cbs.items():
                c.value = wd in offs; c.disabled = not has_off
            days_row.visible = has_off
            save_btn.text = 'حفظ التعديل'; page.update()

        def remove(sh):
            try:
                attendance.delete_shift(sh.id); refresh_all()
            except Exception as ex:
                snack(str(ex))

        save_btn = ft.FilledButton('إضافة وردية', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save)
        rows = []
        for sh in attendance.list_shifts():
            offtxt = 'راحة الشركة' if sh.weekly_off_days is None or str(sh.weekly_off_days).strip() == '' else '، '.join(attendance.WEEKDAY_NAMES[d] for d in sorted(attendance._parse_days(sh.weekly_off_days), key=lambda x: [5, 6, 0, 1, 2, 3, 4].index(x)))
            rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(sh.name)), ft.DataCell(ft.Text(f'{sh.start_time} - {sh.end_time}')),
                                          ft.DataCell(ft.Text('الشركة' if sh.grace_minutes is None else f'{sh.grace_minutes} د')), ft.DataCell(ft.Text(offtxt, size=12)),
                                          ft.DataCell(ft.Row([ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, sh=sh: edit(sh)),
                                                              ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, sh=sh: remove(sh))], spacing=0))]))
        return ft.Column([
            ft.Text('ورديات بدوام مختلف (مثلًا صباحي 08:00-16:00 ومسائي 14:00-22:00). اربط كل موظف بوردية من تبويب "ربط الموظفين"، ومن غير وردية بياخد دوام الشركة. '
                    'التأخير والإضافي والغياب بيتحسبوا على وردية الموظف. الوردية بتنطبق من تاريخ سريان بتحدده في تبويب "ربط الموظفين"، والوردية ممكن تعدّي منتصف الليل (مثلًا ليلي 22:00-06:00) ولو البداية = النهاية تبقى 24 ساعة. بصمة الفجر بتتنسب ليوم بدء الوردية.',
                    size=12, color=theme.TEXT_MUTED),
            ft.Row([name_f, st_f, en_f, gr_f], wrap=True), own_off, days_row,
            ft.Row([save_btn, ft.TextButton('جديد', on_click=clear)]), err,
            ft.Column([ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الوردية', 'الدوام', 'السماحية', 'الراحة الأسبوعية', '']], rows=rows)], scroll=ft.ScrollMode.AUTO)], spacing=10)

    theme.call_without_page_update(page, refresh_all)
    return ft.Column([theme.page_title('الحضور والبصمة', 'بصمات الجهاز وربطها بالغياب في الرواتب'),
                      ft.Container(height=10), tabs.control], expand=True)
