import datetime
import flet as ft
import threading
from .. import services, theme, backup, audit, backup_remote as remote

KIND_LABEL = {'manual': 'يدوية', 'auto': 'تلقائية', 'pre_restore': 'أمان قبل استرجاع', 'pre_update': 'أمان قبل ترقية'}


def _size(n):
    return f'{n / 1048576:.1f} MB' if n >= 1048576 else f'{n / 1024:.0f} KB'


def build_backup(page: ft.Page):
    """النسخ الاحتياطي: نسخة الآن، نسخ تلقائي دوري، قائمة النسخ (تنزيل / استرجاع / حذف)."""
    services.require_action('backup', 'view')
    cfg = backup.get_config()
    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD)) for x in ['النسخة', 'النوع', 'الوقت', 'الحجم', '']], rows=[])
    status = ft.Text('', size=13)
    msg = ft.Text('', size=12, color=theme.SUCCESS, visible=False)
    auto_sw = ft.Switch(label='نسخ تلقائي', value=bool(cfg['auto']))
    hours_f = ft.TextField(label='كل كام ساعة', width=120, dense=True, value=str(cfg['interval_hours']), keyboard_type=ft.KeyboardType.NUMBER)
    keep_f = ft.TextField(label='عدد النسخ المحفوظة', width=150, dense=True, value=str(cfg['keep']), keyboard_type=ft.KeyboardType.NUMBER)
    extra_f = ft.TextField(label='مجلد نسخ إضافي (فلاشة / شبكة) - اختياري', width=380, dense=True, value=cfg['extra_dir'])

    def snack(t):
        page.overlay.append(ft.SnackBar(ft.Text(t), open=True)); page.update()

    def refresh():
        files = backup.list_backups()
        last = backup.last_backup_time()
        age = (datetime.datetime.now() - last).total_seconds() / 3600 if last else None
        status.value = ('آخر نسخة: ' + last.strftime('%Y-%m-%d %H:%M') + f' (من {age:.0f} ساعة)') if last else 'لسه مفيش أي نسخة احتياطية!'
        status.color = theme.SUCCESS if (age is not None and age < 48) else theme.DANGER
        rows = []
        for f in files:
            rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(f['name'], size=12)), ft.DataCell(ft.Text(KIND_LABEL.get(f['kind'], f['kind']), size=12)), ft.DataCell(ft.Text(f['at'].strftime('%Y-%m-%d %H:%M'), size=12)),
                                          ft.DataCell(ft.Text(_size(f['size']), size=12)),
                                          ft.DataCell(ft.Row([ft.IconButton(ft.Icons.DOWNLOAD_OUTLINED, tooltip='تنزيل', on_click=lambda e, p=f['path']: theme.open_or_download_file(page, p)),
                                                              ft.IconButton(ft.Icons.RESTORE, tooltip='استرجاع', icon_color=theme.WARNING, on_click=lambda e, n=f['name']: ask_restore(n)),
                                                              ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip='حذف', icon_color=theme.DANGER, on_click=lambda e, n=f['name']: do_delete(n))], spacing=0))]))
        table.rows = rows

    def run_backup(e):
        try:
            r = backup.backup_now('manual', (services.current_user() or {}).get('username'))
            msg.value = f"تم إنشاء النسخة {r['name']} ({_size(r['size'])})"; msg.visible = True
            refresh(); page.update()
        except Exception as ex:
            snack(f'تعذر النسخ: {ex}')

    def save(e):
        try:
            services.require_action('backup', 'edit')
            backup.save_config(auto=auto_sw.value, interval_hours=int(hours_f.value or 24), keep=int(keep_f.value or 14), extra_dir=(extra_f.value or '').strip())
            snack('تم حفظ إعدادات النسخ')
        except Exception as ex:
            snack(str(ex))

    def do_delete(name):
        try:
            services.require_action('backup', 'delete')
            backup.delete_backup(name); refresh(); page.update()
        except Exception as ex:
            snack(str(ex))

    def ask_restore(name):
        confirm = ft.TextField(label='اكتب  استرجاع  للتأكيد', width=300)
        err = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def go(e):
            if (confirm.value or '').strip() != 'استرجاع':
                err.value = 'اكتب كلمة "استرجاع" بالظبط'; err.visible = True; page.update(); return
            try:
                services.require_action('backup', 'post')
                safety = backup.restore_backup(name)
                dlg.open = False
                msg.value = f'تم الاسترجاع من {name}. نسخة أمان من الحالة السابقة: {safety}. اقفل البرنامج وافتحه تاني عشان البيانات تتحمّل.'; msg.visible = True
                refresh(); page.update()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        dlg = ft.AlertDialog(modal=True, title=ft.Text('استرجاع نسخة احتياطية'),
                             content=ft.Column([ft.Text(f'هيتم استبدال كل البيانات الحالية ببيانات النسخة:\n{name}\nهتتعمل نسخة أمان من الحالة الحالية الأول، ولازم تعيد تشغيل البرنامج بعد الاسترجاع.', size=13), confirm, err], tight=True, spacing=10, width=420),
                             actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(dlg, 'open', False), page.update())), ft.FilledButton('استرجاع', bgcolor=theme.DANGER, on_click=go)])
        page.overlay.append(dlg); dlg.open = True; page.update()


    # ───── النسخ الخارجي (مجلد شبكة / S3 / Google Drive) ─────
    rc = remote.get_config()
    RF = {}

    def rtf(key, label, width=300, password=False, **kw):
        RF[key] = ft.TextField(label=label, value=str(rc.get(key, '')), width=width, dense=True, password=password, can_reveal_password=password, **kw)
        return RF[key]

    def rsw(key, label):
        RF[key] = ft.Switch(label=label, value=bool(rc.get(key)))
        return RF[key]
    gd_auth = ft.Dropdown(label='طريقة الدخول', width=260, dense=True, value=rc['gd_auth'], options=[ft.dropdown.Option('oauth', 'حساب شخصي (OAuth refresh token)'), ft.dropdown.Option('service', 'Service Account (Shared Drive)')])
    rstatus = ft.Column(spacing=2)
    rmsg = ft.Text('', size=12, visible=False)
    rlist = ft.Column(spacing=2)

    def collect():
        v = {k: (c.value if isinstance(c, ft.Switch) else (c.value or '').strip()) for k, c in RF.items()}
        v['gd_auth'] = gd_auth.value
        v['remote_keep'] = int(v.get('remote_keep') or 30)
        return v

    def show(t, ok=True):
        rmsg.value = t; rmsg.color = theme.SUCCESS if ok else theme.DANGER; rmsg.visible = True; page.update()

    def refresh_remote():
        rstatus.controls = []
        st = remote.status()
        if not st:
            rstatus.controls = [ft.Text('مفيش مكان خارجي مفعّل - النسخ على الجهاز ده بس (مش حماية كاملة لو الجهاز اتعطل أو اتسرق).', size=12, color=theme.WARNING)]
        for slot, info in st.items():
            last = info['last'] or {}
            ok = last.get('ok')
            line = f"{info['label']}: " + ('آخر رفع ' + last.get('at', '').replace('T', ' ') if ok else ('فشل: ' + str(last.get('error')) if last else 'لسه ما اترفعش حاجة')) + (f" - {info['pending']} نسخة منتظرة الرفع" if info['pending'] else '')
            rstatus.controls.append(ft.Text(line, size=12, color=theme.SUCCESS if ok and not info['pending'] else (theme.DANGER if ok is False else theme.WARNING)))

    def bg(fn, busy_msg):
        def run():
            try:
                show(busy_msg)
                r = fn()
                show(r if isinstance(r, str) else 'تم', True)
            except Exception as ex:
                show(str(ex), False)
            refresh_remote(); refresh(); page.update()
        threading.Thread(target=run, daemon=True).start()

    def save_remote(e):
        try:
            remote.save_config(**collect())
            refresh_remote(); show('تم حفظ إعدادات النسخ الخارجي')
        except Exception as ex:
            show(str(ex), False)

    def test(slot):
        def go():
            return remote.test_slot(slot, **collect())
        bg(go, 'بجرّب الاتصال...')

    def sync_now(e):
        def go():
            r = remote.sync_now()
            return '؛ '.join(f"{remote.SLOTS[k]}: " + (f"فشل ({v['error']})" if v['error'] else f"اترفع {v['uploaded']}") for k, v in r.items()) or 'مفيش حاجة جديدة للرفع'
        bg(go, 'برفع النسخ...')

    def load_remote(slot):
        def go():
            rows = remote.list_remote(slot)
            rlist.controls = [ft.Row([ft.Text(f"{r['name']}  ·  {r['at']:%Y-%m-%d %H:%M}  ·  {_size(r['size'])}", size=12, expand=True),
                                      ft.TextButton('جلب للجهاز', on_click=lambda e, n=r['name']: fetch(slot, n))]) for r in rows[:30]] or [ft.Text('مفيش نسخ في المكان ده', size=12)]
            return f"{len(rows)} نسخة في {remote.SLOTS[slot]}"
        bg(go, 'بقرا القائمة...')

    def fetch(slot, name):
        bg(lambda: f"اتجابت {remote.fetch_remote(slot, name)} - تقدر تسترجعها من الجدول تحت", 'بنزّل النسخة...')

    def tile(slot, controls):
        return ft.ExpansionTile(title=ft.Text(remote.SLOTS[slot]), expanded=bool(rc.get({'folder': 'folder_enabled', 's3': 's3_enabled', 'gdrive': 'gd_enabled'}[slot])),
                                controls=[ft.Container(ft.Column(controls + [ft.Row([ft.OutlinedButton('تجربة الاتصال', icon=ft.Icons.WIFI_TETHERING, on_click=lambda e, s=slot: test(s)),
                                                                                  ft.OutlinedButton('عرض النسخ البعيدة', icon=ft.Icons.LIST, on_click=lambda e, s=slot: load_remote(s))], spacing=8)], spacing=8), padding=10)])
    remote_card = theme.card(ft.Column([
        ft.Text('النسخ الاحتياطي الخارجي (خارج الجهاز)', weight=ft.FontWeight.BOLD),
        ft.Text('كل نسخة جديدة بتترفع تلقائيًا للأماكن المفعّلة. لو الرفع فشل (النت قاطع مثلًا) البرنامج بيعيد المحاولة لوحده. النسخة المحلية دايمًا سليمة.', size=11.5, color=theme.TEXT_MUTED),
        rstatus, rmsg,
        tile('folder', [rsw('folder_enabled', 'تفعيل'), rtf('folder_path', 'المسار (مثال: \\\\server\\backups أو E:\\erp أو /mnt/nas/erp)', 460)]),
        tile('s3', [rsw('s3_enabled', 'تفعيل'), ft.Row([rtf('s3_endpoint', 'Endpoint (https://s3.amazonaws.com أو رابط R2/MinIO)', 380), rtf('s3_region', 'Region', 130)], wrap=True),
                    ft.Row([rtf('s3_bucket', 'Bucket', 200), rtf('s3_prefix', 'مجلد داخل الـ Bucket', 200), rsw('s3_path_style', 'Path-style (فعّلها لـ MinIO/R2)')], wrap=True),
                    ft.Row([rtf('s3_access_key', 'Access Key', 240), rtf('s3_secret_key', 'Secret Key', 300, password=True)], wrap=True)]),
        tile('gdrive', [rsw('gd_enabled', 'تفعيل'), gd_auth, rtf('gd_folder_id', 'Folder ID (من رابط المجلد)', 380),
                        ft.Row([rtf('gd_client_id', 'Client ID', 300), rtf('gd_client_secret', 'Client Secret', 260, password=True), rtf('gd_refresh_token', 'Refresh Token', 300, password=True)], wrap=True),
                        rtf('gd_service_secret', 'أو: مسار ملف JSON / محتواه لحساب الخدمة', 560, password=True)]),
        ft.Divider(height=1),
        ft.Row([rsw('encrypt', 'تشفير النسخ قبل الرفع (AES-256)'), rtf('passphrase', 'كلمة سر التشفير', 260, password=True), rtf('remote_keep', 'عدد النسخ البعيدة المحفوظة', 170, keyboard_type=ft.KeyboardType.NUMBER)], wrap=True, spacing=10),
        ft.Text('تحذير: لو فعّلت التشفير وضاعت كلمة السر، النسخ المشفّرة مستحيل تتفتح. احتفظ بها في مكان منفصل عن الجهاز.', size=11.5, color=theme.WARNING),
        ft.Row([ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, on_click=save_remote), ft.OutlinedButton('ارفع المنتظر الآن', icon=ft.Icons.CLOUD_UPLOAD_OUTLINED, on_click=sync_now)], spacing=8),
        rlist,
    ], spacing=8))
    refresh_remote()

    from .. import restore_drill
    drill_txt = ft.Text('', size=12)
    drill_sw = ft.Switch(label='فحص دوري تلقائي', value=restore_drill.get_config()['enabled'])
    drill_days = ft.TextField(label='كل كام يوم', width=110, dense=True, value=str(restore_drill.get_config()['days']), keyboard_type=ft.KeyboardType.NUMBER)

    def refresh_drill():
        r = restore_drill.last()
        warn = ''
        try:
            if remote.enabled_slots() and not remote.get_config()['encrypt']:
                warn = '  ⚠ النسخ البعيدة غير مشفّرة - فعّل التشفير فوق.'
        except Exception:
            pass
        if not r:
            drill_txt.value = 'لسه ما اتعملش فحص استرجاع.' + warn; drill_txt.color = theme.WARNING
        else:
            rem = r.get('remote')
            parts = [('نجح ✔' if r['ok'] else 'فشل ✘') + f" - {r['at'].replace('T', ' ')} ({r.get('secs', 0)} ث)", f"النسخة: {r.get('backup')}",
                     'استرجاع كامل في مكان مؤقت' if r.get('level') == 'full' else ('فحص القائمة فقط (مفيش صلاحية إنشاء قاعدة مؤقتة)' if r.get('level') == 'list' else '')]
            if rem:
                parts.append(f"النسخة البعيدة ({remote.SLOTS.get(rem['slot'], rem['slot'])}): " + ('سليمة' + (' ومشفّرة وتفتح بكلمة السر' if rem.get('encrypted') else '') if rem['ok'] else 'فشل - ' + str(rem.get('error'))))
            if r.get('error') and not (rem and not rem['ok']):
                parts.append(str(r['error']))
            drill_txt.value = ' · '.join(p for p in parts if p) + warn
            drill_txt.color = theme.SUCCESS if r['ok'] else theme.DANGER

    def run_drill_now(e):
        def go():
            r = restore_drill.run_drill()
            return 'فحص الاسترجاع نجح ✔' if r['ok'] else 'فحص الاسترجاع فشل: ' + str(r['error'])
        bg(go, 'بجرّب الاسترجاع فعليًا (ممكن ياخد دقيقة)...')
        refresh_drill()

    def save_drill(e):
        try:
            services.require_action('backup', 'edit')
            restore_drill.save_config(enabled=drill_sw.value, days=int(drill_days.value or 7)); snack('تم الحفظ')
        except Exception as ex:
            snack(str(ex))
    refresh_drill()
    _orig_bg_refresh = refresh_remote

    def refresh_remote():          # بعد أي عملية خلفية حدّث فحص الاسترجاع كمان
        _orig_bg_refresh(); refresh_drill()
    drill_card = theme.card(ft.Column([
        ft.Text('فحص الاسترجاع (النسخة بتتفتح فعلًا؟)', weight=ft.FontWeight.BOLD),
        ft.Text('السيرفر بيسترجع آخر نسخة في مكان مؤقت ويتأكد إن البيانات سليمة، وبيجيب آخر نسخة بعيدة ويفك تشفيرها. لو فشل بيوصلك تنبيه من بوابة المراقبة.', size=11.5, color=theme.TEXT_MUTED),
        drill_txt, ft.Row([drill_sw, drill_days, ft.OutlinedButton('حفظ', on_click=save_drill), ft.FilledButton('افحص الاسترجاع الآن', icon=ft.Icons.FACT_CHECK_OUTLINED, on_click=run_drill_now)], wrap=True, spacing=10)], spacing=8))

    refresh()
    return ft.Column([
        theme.page_title('النسخ الاحتياطي والاسترجاع', 'حماية بياناتك: نسخ متسق وفحص سلامة وقت النسخ، ونسخ تلقائي، واسترجاع بنسخة أمان'),
        theme.card(ft.Column([status, msg, ft.Row([theme.guard_submit(ft.FilledButton('نسخ احتياطي الآن', icon=ft.Icons.BACKUP_OUTLINED, bgcolor=theme.PRIMARY, on_click=run_backup))], spacing=10)], spacing=8)),
        theme.card(ft.Column([ft.Text('إعدادات النسخ التلقائي', weight=ft.FontWeight.BOLD), ft.Row([auto_sw, hours_f, keep_f, extra_f, ft.OutlinedButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, on_click=save)], wrap=True, spacing=10),
                              ft.Text('النسخ التلقائي بيشتغل وقت ما البرنامج مفتوح (عند فتحه وكل نص ساعة بيتأكد). نسخ "أمان قبل استرجاع" ما بتتمسحش تلقائيًا.', size=11.5, color=theme.TEXT_MUTED)], spacing=8)),
        remote_card,
        drill_card,
        theme.card(ft.Column([ft.Text('النسخ المحفوظة', weight=ft.FontWeight.BOLD), theme.h_scroll(table)], spacing=8), expand=True),
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
