import threading
import flet as ft
from .. import services, theme, pg_migrate
from ..db import IS_SQLITE


def build_database(page: ft.Page):
    """قاعدة البيانات: الحالة الحالية، الاتصال بـPostgreSQL (اختبار + حفظ)، ونقل بيانات SQLite الحالية إليه."""
    services.require_action('settings', 'view')
    info = pg_migrate.current_info()
    host_f = ft.TextField(label='السيرفر (host)', value='localhost', width=220, dense=True)
    port_f = ft.TextField(label='المنفذ', value='5432', width=100, dense=True, keyboard_type=ft.KeyboardType.NUMBER)
    db_f = ft.TextField(label='اسم القاعدة', value='erp', width=170, dense=True)
    user_f = ft.TextField(label='المستخدم', value='postgres', width=170, dense=True)
    pw_f = ft.TextField(label='كلمة المرور', width=190, dense=True, password=True, can_reveal_password=True)
    msg = ft.Text('', size=12, visible=False)
    prog = ft.Text('', size=12, color=theme.TEXT_MUTED)
    report_col = ft.Column(spacing=4)
    state = {'url': None, 'empty': False, 'busy': False}

    def say(text, color=None, ok=None):
        msg.value = text; msg.visible = bool(text)
        msg.color = color or (theme.SUCCESS if ok else theme.DANGER if ok is False else theme.TEXT_MUTED)
        page.update()

    def current_url():
        return pg_migrate.build_url(host_f.value.strip(), port_f.value.strip(), db_f.value.strip(), user_f.value.strip(), pw_f.value)

    def test(e=None):
        try:
            r = pg_migrate.test_connection(current_url())
        except Exception as ex:
            say(str(ex), ok=False); return None
        state['empty'] = r['empty']
        say((r['message'] + (f" — PostgreSQL {r['version']}" if r['version'] else '')), ok=r['ok'])
        return r

    def save(e=None):
        try:
            pg_migrate.save_url(current_url())
            say('تم حفظ الإعداد. اقفل البرنامج/السيرفر وشغّله تاني عشان يشتغل على PostgreSQL. (لو عايز تنقل بياناتك الحالية استخدم زر النقل قبل إعادة التشغيل)', ok=True)
        except Exception as ex:
            say(str(ex), ok=False)

    def back_to_sqlite(e=None):
        try:
            pg_migrate.clear_url()
            say('اتشال إعداد PostgreSQL. أعد تشغيل البرنامج للرجوع لـ SQLite المحلي.', ok=True)
        except Exception as ex:
            say(str(ex), ok=False)

    def do_migrate(e=None):
        if state['busy']:
            return
        r = test()
        if not r or not r['ok']:
            return
        if not r['empty']:
            say('القاعدة الهدف فيها بيانات - لازم تكون قاعدة جديدة فاضية.', ok=False); return
        url = current_url()
        user = services.current_user()
        state['busy'] = True
        report_col.controls = []

        def worker():
            services.bind_thread_user(user)
            try:
                rep = pg_migrate.migrate(url, progress=lambda m: (setattr(prog, 'value', m), page.update()))
                lines = [ft.Text(f"تم نقل {rep['rows']:,} صف في {rep['seconds']} ثانية.", color=theme.SUCCESS, weight=ft.FontWeight.BOLD)]
                if rep['skipped']:
                    lines.append(ft.Text(f"تخطّى {len(rep['skipped'])} صف (مراجع ناقصة في البيانات القديمة) — أول 10:", color=theme.WARNING))
                    lines += [ft.Text(f"{s_['table']} #{s_['id']}: {s_['error'][:110]}", size=11) for s_ in rep['skipped'][:10]]
                lines.append(ft.Text('الخطوة الجاية: اضغط "حفظ كقاعدة البرنامج" ثم أعد تشغيل البرنامج.', size=12, color=theme.TEXT_MUTED))
                report_col.controls = lines
                prog.value = ''
            except Exception as ex:
                report_col.controls = [ft.Text(f'فشل النقل: {ex}', color=theme.DANGER)]
                prog.value = ''
            finally:
                state['busy'] = False
                page.update()
        threading.Thread(target=worker, daemon=True).start()

    def ask_migrate(e):
        dlg = ft.AlertDialog(modal=True, title=ft.Text('نقل البيانات إلى PostgreSQL'),
                             content=ft.Text('هينسخ كل بيانات SQLite الحالية للقاعدة الجديدة (الفاضية). ملف SQLite الأصلي مش هيتغيّر. اوقف الشغل على البرنامج من أي جهاز تاني أثناء النقل. متأكد؟'),
                             actions=[ft.TextButton('إلغاء', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())),
                                      ft.FilledButton('ابدأ النقل', bgcolor=theme.PRIMARY, on_click=lambda ev: (setattr(dlg, 'open', False), page.update(), do_migrate()))])
        page.overlay.append(dlg); dlg.open = True; page.update()

    size_mb = info.get('size', 0) / 1048576
    status = theme.card(ft.Column([
        ft.Text('القاعدة الحالية', size=15, weight=ft.FontWeight.BOLD),
        ft.Row([ft.Icon(ft.Icons.STORAGE, color=theme.PRIMARY), ft.Text(f"{info['kind']} {info.get('version', '')}", size=14, weight=ft.FontWeight.W_600),
                ft.Text(f"{size_mb:,.1f} MB", size=12, color=theme.TEXT_MUTED)], spacing=8),
        ft.Text(info['url'], size=12, color=theme.TEXT_MUTED, selectable=True),
        *([ft.Text(f"مضبوط للتشغيل القادم: {info['configured']} (بعد إعادة التشغيل)", size=12, color=theme.WARNING)] if info.get('configured') and (IS_SQLITE or info['configured'] != info['url']) else []),
        *([ft.Text('تنبيه: متغير البيئة ERP_DATABASE_URL شغّال وبيتغلب على الإعداد المحفوظ هنا.', size=12, color=theme.WARNING)] if info.get('env_override') else []),
        *([ft.Text(f"تعذر قراءة حالة القاعدة: {info['error']}", size=12, color=theme.DANGER)] if info.get('error') else []),
    ], spacing=6))

    form = theme.card(ft.Column([
        ft.Text('الاتصال بـ PostgreSQL', size=15, weight=ft.FontWeight.BOLD),
        ft.Text('أنشئ قاعدة فاضية (مثلًا erp) ومستخدم له كل الصلاحيات عليها، واكتب بياناتها هنا. كلمة السر بتتخزّن في ملف database.json على السيرفر.', size=11, color=theme.TEXT_MUTED),
        ft.Row([host_f, port_f, db_f, user_f, pw_f], wrap=True, spacing=10),
        ft.Row([ft.OutlinedButton('اختبار الاتصال', icon=ft.Icons.NETWORK_CHECK, on_click=test),
                ft.FilledButton('حفظ كقاعدة البرنامج', icon=ft.Icons.SAVE, bgcolor=theme.PRIMARY, on_click=save),
                *([ft.OutlinedButton('نقل بيانات SQLite الحالية إلى هذه القاعدة', icon=ft.Icons.DRIVE_FILE_MOVE_OUTLINE, on_click=ask_migrate)] if IS_SQLITE else []),
                *([ft.TextButton('الرجوع إلى SQLite', icon=ft.Icons.UNDO, on_click=back_to_sqlite)] if not IS_SQLITE else [])], wrap=True, spacing=10),
        msg, prog, report_col,
    ], spacing=10))

    notes = theme.card(ft.Column([
        ft.Text('ملاحظات', size=15, weight=ft.FontWeight.BOLD),
        ft.Text('• النسخ الاحتياطي مع PostgreSQL بيستخدم pg_dump/pg_restore، فلازم أدوات PostgreSQL (client tools) تكون مثبتة على جهاز السيرفر.', size=12),
        ft.Text('• تغيير القاعدة بيتطلب إعادة تشغيل البرنامج/السيرفر.', size=12),
        ft.Text('• المرفقات (صور الأصناف، ملفات الموظفين...) بتفضل ملفات على جهاز السيرفر مش جوه القاعدة.', size=12),
    ], spacing=4))
    return ft.Column([theme.page_title('قاعدة البيانات', 'SQLite المحلي أو PostgreSQL للسيرفر وتعدد المستخدمين والفروع'), status, form, notes], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
