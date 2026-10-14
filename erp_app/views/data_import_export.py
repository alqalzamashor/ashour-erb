import os
import flet as ft
from .. import services, theme, import_export
from ..import_export_ext import raw_tables, export_raw_table, export_all_tables

GROUP_ORDER = ['الأصناف والمخزون', 'المبيعات', 'المشتريات', 'المحاسبة', 'الأصول الثابتة', 'الموارد البشرية', 'المنظمة', 'الكاشير والمطعم', 'أخرى']


def build_data_import_export(page: ft.Page):
    """استيراد وتصدير جماعي لبيانات النظام بقوالب Excel (كل الأنواع الأساسية)، وتصدير أي جدول من قاعدة البيانات
    أو كلها في ملف واحد."""
    me = services.current_user() or {}
    is_admin = me.get('role') == 'admin'

    def entity_options(filter_text=''):
        ft_ = (filter_text or '').strip()
        items = sorted(import_export.ENTITY_SPECS.items(), key=lambda kv: (GROUP_ORDER.index(kv[1].get('group', 'أخرى')) if kv[1].get('group', 'أخرى') in GROUP_ORDER else 99, kv[1]['label']))
        return [ft.dropdown.Option(k, f"{sp.get('group', 'أخرى')} ▸ {sp['label']}") for k, sp in items if not ft_ or ft_ in sp['label'] or ft_ in sp.get('group', '')]

    entity_dd = ft.Dropdown(label='نوع البيانات', width=360, options=entity_options(), value='products')
    filter_f = ft.TextField(label='بحث في الأنواع', width=200, prefix_icon=ft.Icons.SEARCH)
    status_text = ft.Text('', visible=False)
    result_table = ft.DataTable(columns=[ft.DataColumn(ft.Text('رقم الصف')), ft.DataColumn(ft.Text('سبب الخطأ'))], rows=[], visible=False)
    result_summary = ft.Text('', visible=False)
    note_text = ft.Text('', size=12, color=theme.TEXT_MUTED)

    def exports_dir():
        d = services.downloads_dir()
        os.makedirs(d, exist_ok=True)
        return d

    def open_file(path):
        try:
            theme.open_or_download_file(page, path)
        except Exception:
            pass

    def show_status(message, color=theme.SUCCESS):
        status_text.value = message; status_text.color = color; status_text.visible = True
        page.update()

    def on_filter(e=None):
        entity_dd.options = entity_options(filter_f.value)
        if entity_dd.options and entity_dd.value not in [o.key for o in entity_dd.options]:
            entity_dd.value = entity_dd.options[0].key
        page.update()

    def download_template(e):
        try:
            spec = import_export.ENTITY_SPECS[entity_dd.value]
            path = os.path.join(exports_dir(), f"قالب_{spec['label']}.xlsx".replace('/', '-'))
            spec['template'](path)
            open_file(path)
            show_status(f"تم إنشاء القالب وفتحه: {path}")
        except Exception as ex:
            show_status(f'تعذر إنشاء القالب: {ex}', theme.DANGER)

    def export_current(e):
        try:
            spec = import_export.ENTITY_SPECS[entity_dd.value]
            path = os.path.join(exports_dir(), f"تصدير_{spec['label']}.xlsx".replace('/', '-'))
            spec['export'](path)
            open_file(path)
            show_status(f"تم تصدير البيانات الحالية: {path}")
        except Exception as ex:
            show_status(f'تعذر التصدير: {ex}', theme.DANGER)

    progress_bar = ft.ProgressBar(value=0, width=360, visible=False, color=theme.PRIMARY, bgcolor=theme.SURFACE_ALT)
    progress_text = ft.Text('', size=12, color=theme.TEXT_MUTED, visible=False)
    busy = {'running': False}

    def set_busy(on):
        busy['running'] = on
        imp_btn.disabled = on; tpl_btn.disabled = on or not import_export.ENTITY_SPECS[entity_dd.value].get('template')
        progress_bar.visible = on; progress_text.visible = on
        if not on:
            progress_bar.value = 0
        page.update()

    def on_progress(done, total):
        progress_bar.value = (done / total) if total else 0
        progress_text.value = f'جاري الاستيراد... {done:,} من {total:,} صف'
        page.update()

    def show_result(result):
        result_summary.value = (f"تم الاستيراد: {result['created']} سجل جديد، {result['updated']} سجل مُحدَّث"
                                + (f"، {len(result['errors'])} صف فيه خطأ (اتجاهل ولم يُستورد)" if result['errors'] else ""))
        result_summary.color = theme.DANGER if result['errors'] else theme.SUCCESS
        result_summary.visible = True
        if result['errors']:
            result_table.rows = [ft.DataRow(cells=[ft.DataCell(ft.Text(str(row_num))), ft.DataCell(ft.Text(msg))]) for row_num, msg in result['errors'][:300]]
            result_table.visible = True
            if len(result['errors']) > 300:
                result_summary.value += f" (معروض أول 300 خطأ من {len(result['errors']):,})"
        else:
            result_table.visible = False

    async def do_import(e):
        if busy['running']:
            return
        try:
            path = await theme.pick_file(page, 'اختر ملف Excel المملوء', ['xlsx'])
            if not path:
                return
            spec = import_export.ENTITY_SPECS[entity_dd.value]
        except Exception as ex:
            show_status(f'تعذر الاستيراد: {ex}', theme.DANGER)
            return

        _u = services.current_user()

        def worker():
            services.bind_thread_user(_u)
            try:
                import_export.set_progress_callback(on_progress)
                result = spec['import'](path)
                show_result(result)
            except Exception as ex:
                show_status(f'تعذر الاستيراد: {ex}', theme.DANGER)
            finally:
                import_export.set_progress_callback(None)
                set_busy(False)
        set_busy(True)
        status_text.visible = False
        # الاستيراد الكبير بيتعمل في خيط خلفي وشريط التقدّم بيتحدّث - الشاشة ما بتقفلش
        import threading
        threading.Thread(target=worker, daemon=True).start()

    # ---------------- تصدير أي جدول من القاعدة ----------------
    raw = raw_tables(is_admin)
    raw_dd = ft.Dropdown(label='جدول قاعدة البيانات', width=360, options=[ft.dropdown.Option(n, f'{lbl}  ({cnt} صف)') for n, lbl, cnt in raw], value=raw[0][0] if raw else None)
    raw_status = ft.Text('', visible=False)

    def raw_msg(msg, color=theme.SUCCESS):
        raw_status.value = msg; raw_status.color = color; raw_status.visible = True
        page.update()

    def export_raw(e):
        try:
            label = next((l for n, l, c in raw if n == raw_dd.value), raw_dd.value)
            res = export_raw_table(raw_dd.value, os.path.join(exports_dir(), f"جدول_{label}.xlsx".replace('/', '-')))
            open_file(res['path']); raw_msg(f"تم تصدير {res['rows']} صف من \"{label}\": {res['path']}")
        except Exception as ex:
            raw_msg(f'تعذر التصدير: {ex}', theme.DANGER)

    def export_all(e):
        try:
            raw_msg('جاري تجهيز الملف الكامل...', theme.TEXT_MUTED)
            res = export_all_tables(os.path.join(exports_dir(), 'تصدير_كل_الجداول.xlsx'))
            open_file(res['path']); raw_msg(f"تم تصدير {res['tables']} جدول ({res['rows']:,} صف) في ملف واحد: {res['path']}")
        except Exception as ex:
            raw_msg(f'تعذر التصدير: {ex}', theme.DANGER)

    def refresh_note(e=None):
        sp = import_export.ENTITY_SPECS.get(entity_dd.value)
        note_text.value = '' if not sp else ('الأعمدة اللي عليها * إجبارية. حمّل القالب أولًا لتشوف الأعمدة والتعليمات.' if sp.get('import') else 'هذا النوع للتصدير فقط.')
        has_import = bool(sp and sp.get('import'))
        tpl_btn.disabled = not (sp and sp.get('template')); imp_btn.disabled = not has_import
        page.update()

    entity_dd.on_change = refresh_note
    filter_f.on_change = on_filter
    tpl_btn = ft.FilledButton('تحميل قالب فارغ', icon=ft.Icons.DOWNLOAD_OUTLINED, bgcolor=theme.PRIMARY, on_click=download_template)
    imp_btn = ft.FilledButton('تصفح واستيراد ملف Excel...', icon=ft.Icons.UPLOAD_FILE, bgcolor=theme.PRIMARY, on_click=do_import)
    refresh_note()
    return ft.Column([
        theme.page_title('استيراد وتصدير البيانات', 'استورد وصدّر كل بيانات النظام بقوالب Excel: أصناف (يُباع/يُشترى)، عملاء، موردين، موظفين، حسابات، فروع، أسعار، موازنات... وتصدير أي جدول'),
        ft.Container(height=10),
        theme.card(ft.Column([
            theme.section_title('استيراد وتصدير بقوالب', ft.Icons.SWAP_VERT),
            ft.Text('1) اختر نوع البيانات   2) حمّل القالب الفارغ واملأه   3) اضغط تصفح واستيراد واختار الملف', color=theme.TEXT_MUTED, size=12),
            ft.Row([entity_dd, filter_f], wrap=True, spacing=12), note_text,
            ft.Row([tpl_btn, ft.OutlinedButton('تصدير البيانات الحالية', icon=ft.Icons.FILE_UPLOAD_OUTLINED, on_click=export_current)], wrap=True, spacing=12),
            ft.Divider(), imp_btn, progress_bar, progress_text, status_text], spacing=10)),
        ft.Container(height=10), result_summary, ft.Container(content=theme.h_scroll(result_table), visible=True),
        ft.Container(height=10),
        theme.card(ft.Column([
            theme.section_title('تصدير أي جدول من قاعدة البيانات', ft.Icons.STORAGE_OUTLINED),
            ft.Text(f'كل جداول النظام ({len(raw)} جدول: فواتير، قيود، حركات مخزون، رواتب، أصول، سندات...). الأعمدة المرتبطة (العميل، الصنف، الحساب...) بتتحوّل لأسماء مقروءة بجانب المعرّف.'
                    + ('' if is_admin else ' جداول المستخدمين والرسائل وجدول الأعمال لمدير النظام فقط.'), color=theme.TEXT_MUTED, size=12),
            ft.Row([raw_dd, ft.OutlinedButton('تصدير الجدول', icon=ft.Icons.FILE_UPLOAD_OUTLINED, on_click=export_raw),
                    ft.FilledButton('تصدير كل الجداول في ملف واحد', icon=ft.Icons.FOLDER_ZIP_OUTLINED, bgcolor=theme.PRIMARY, on_click=export_all)], wrap=True, spacing=12), raw_status], spacing=10)),
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=6)
