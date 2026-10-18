"""طباعة أي شاشة: بنقرأ العناصر الظاهرة (العنوان، الفلاتر، بطاقات الأرقام، وكل الجداول بكل صفوفها حتى لو الجدول مترقّم صفحات)
ونعمل منها PDF عربي (RTL) جاهز للطباعة - بيتفتح في المتصفح ومنه تطبع. نفس الزر شغّال على أي شاشة وأي نافذة مفتوحة."""
import datetime
import os
import re
from xml.sax.saxutils import escape

import flet as ft

CHILD_ATTRS = ('controls', 'content', 'rows', 'cells', 'tabs', 'actions', 'leading', 'trailing')
ACTION_HEADERS = ('الإجراءات', 'إجراءات', 'اجراءات', 'Actions')
_NUM = re.compile(r'^[\d,.\-/%:+ ]+[^\d\s]{0,12}$')


def _lab(x):
    return x.strip() if isinstance(x, str) else _text_of(x).strip()


def _text_of(c, depth=0):
    """نص خلية: كل النصوص/القيم جواها (النصوص بس - الأيقونات والأزرار وCheckbox بتتجاهل)."""
    if c is None or depth > 8 or isinstance(c, (str, int, float, bool)):
        return ''
    if getattr(c, 'visible', True) is False:
        return ''
    if isinstance(c, ft.Text):
        return '' if c.value is None else str(c.value)
    if isinstance(c, ft.TextField):
        return '' if c.value is None else str(c.value)
    if isinstance(c, ft.Dropdown):
        return _dd_text(c)
    parts = []
    for a in ('content', 'controls', 'label'):
        v = getattr(c, a, None)
        for x in (v if isinstance(v, list) else [v]):
            t = _text_of(x, depth + 1)
            if t:
                parts.append(t)
    return ' '.join(parts)


def _dd_text(dd):
    for o in (getattr(dd, 'options', None) or []):
        if str(getattr(o, 'key', None)) == str(dd.value):
            return str(getattr(o, 'text', None) or getattr(o, 'key', '') or '')
    return '' if dd.value is None else str(dd.value)


def _table_data(t):
    rows_src = getattr(t, '_erp_print_rows', None)
    rows = None
    if callable(rows_src):
        try:
            rows = rows_src()
        except Exception:
            rows = None
    if rows is None:
        rows = list(t.rows or [])
    heads = [_lab(c.label) for c in t.columns]
    body = [[_text_of(cell.content).strip() for cell in r.cells] for r in rows]
    keep = []
    for i, h in enumerate(heads):
        if h in ACTION_HEADERS or (h == '' and not any(i < len(r) and r[i] for r in body)):
            continue
        keep.append(i)
    return {'columns': [heads[i] for i in keep], 'rows': [[(r[i] if i < len(r) else '') for i in keep] for r in body], 'caption': ''}


def extract(root):
    """يرجّع {'filters': [(اسم, قيمة)], 'stats': [(اسم, قيمة)], 'tables': [{'columns','rows','caption'}]}"""
    out = {'filters': [], 'stats': [], 'tables': []}
    seen = set()
    state = {'caption': ''}

    def walk(c, depth=0):
        if c is None or isinstance(c, (str, int, float, bool)) or depth > 80 or id(c) in seen:
            return
        seen.add(id(c))
        if getattr(c, 'visible', True) is False:
            return
        src = getattr(c, '_erp_src_table', None)
        if isinstance(c, ft.DataTable) or src is not None:
            t = _table_data(c if isinstance(c, ft.DataTable) else src)
            sig = (tuple(t['columns']), tuple(map(tuple, t['rows'])))
            if t['rows'] and t['columns'] and sig not in state.setdefault('sigs', set()):       # نسخة العنوان الثابت بتتكرر - نتجاهلها
                state['sigs'].add(sig)
                t['caption'] = state['caption']; state['caption'] = ''
                out['tables'].append(t)
            return
        if isinstance(c, ft.Text):
            v = (c.value or '').strip()
            if v and len(v) <= 60 and (c.size or 0) >= 13:
                state['caption'] = v
            return
        if isinstance(c, ft.TextField):
            if getattr(c, 'password', False) or not c.label or c.value in (None, ''):
                return
            out['filters'].append((_lab(c.label), str(c.value))); return
        if isinstance(c, ft.Dropdown):
            if c.label and c.value not in (None, ''):
                out['filters'].append((_lab(c.label), _dd_text(c)))
            return
        if isinstance(c, ft.Checkbox):
            if c.label and c.value:
                out['filters'].append((_lab(c.label), 'نعم'))
            return
        if isinstance(c, ft.Column):
            kids = [k for k in (c.controls or []) if getattr(k, 'visible', True) is not False]
            if 2 <= len(kids) <= 3 and all(isinstance(k, ft.Text) for k in kids) and _NUM.match((kids[1].value or '').strip() or 'x'):
                out['stats'].append(((kids[0].value or '').strip(), (kids[1].value or '').strip())); return
        for a in CHILD_ATTRS:
            v = getattr(c, a, None)
            if isinstance(v, list):
                for x in v:
                    walk(x, depth + 1)
            elif v is not None:
                walk(v, depth + 1)

    walk(root)
    return out


def _fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from .invoice_pdf import FONT_CANDIDATES, FONT_CANDIDATES_BOLD
    reg = next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)
    bold = next((f for f in FONT_CANDIDATES_BOLD if os.path.exists(f)), None)
    name, bname = 'Helvetica', 'Helvetica-Bold'
    try:
        if reg:
            pdfmetrics.registerFont(TTFont('ERPPrint', reg)); name = 'ERPPrint'; bname = name
        if bold:
            pdfmetrics.registerFont(TTFont('ERPPrintBold', bold)); bname = 'ERPPrintBold'
    except Exception:
        pass
    return name, bname


def build_pdf(data, title, path, rtl=True, subtitle=''):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
    from .report_export import _shape_ar, _company
    shape = _shape_ar if rtl else (lambda s: str(s))
    al = TA_RIGHT if rtl else TA_LEFT
    font, bold = _fonts()
    maxcols = max([len(t['columns']) for t in data['tables']] or [0])
    size = landscape(A4) if maxcols > 5 else A4
    margin = 28
    width = size[0] - 2 * margin
    fs = 9 if maxcols <= 6 else 8 if maxcols <= 9 else 7 if maxcols <= 13 else 6
    P = lambda txt, st: Paragraph(escape(shape(txt)), st)
    st_norm = ParagraphStyle('n', fontName=font, fontSize=fs, leading=fs + 3, alignment=al)
    st_head = ParagraphStyle('h', fontName=bold, fontSize=fs, leading=fs + 3, alignment=al, textColor=colors.white)
    st_meta = ParagraphStyle('m', fontName=font, fontSize=8, leading=11, alignment=al, textColor=colors.HexColor('#4B5563'))
    st_cap = ParagraphStyle('c', fontName=bold, fontSize=10, leading=14, alignment=al, textColor=colors.HexColor('#0F5A45'))
    st_title = ParagraphStyle('t', fontName=bold, fontSize=13, leading=17, alignment=TA_CENTER, textColor=colors.white)
    st_co = ParagraphStyle('co', fontName=bold, fontSize=14, leading=18, alignment=al)
    st_date = ParagraphStyle('d', fontName=font, fontSize=8, leading=11, alignment=TA_LEFT if rtl else TA_RIGHT, textColor=colors.HexColor('#6B7280'))
    co = _company()
    co_name = (co.name if co and getattr(co, 'name', '') else '')
    story = []
    head_l = [P(('تاريخ الطباعة: ' if rtl else 'Printed: ') + datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), st_date)]
    head_r = [P(co_name, st_co)] if co_name else [P('', st_co)]
    ht = Table([[head_l, head_r] if rtl else [head_r, head_l]], colWidths=[width * 0.4, width * 0.6] if rtl else [width * 0.6, width * 0.4])
    ht.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                            ('LINEBELOW', (0, 0), (-1, 0), 1.2, colors.HexColor('#1A7A5E')), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    banner = Table([[P(title + (f' - {subtitle}' if subtitle else ''), st_title)]], colWidths=[width])
    banner.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1F2937')), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    story += [ht, Spacer(1, 8), banner, Spacer(1, 8)]
    if data['filters']:
        story.append(P(' | '.join(f'{k}: {v}' for k, v in data['filters']), st_meta)); story.append(Spacer(1, 4))
    if data['stats']:
        story.append(P(' | '.join(f'{k}: {v}' for k, v in data['stats']), ParagraphStyle('s', parent=st_meta, fontName=bold, textColor=colors.HexColor('#0F5A45'), fontSize=9)))
        story.append(Spacer(1, 6))
    if not data['tables']:
        story.append(P('لا توجد جداول في الشاشة دي للطباعة' if rtl else 'No tables on this screen to print', st_norm))
    for t in data['tables']:
        cols, rows = t['columns'], t['rows']
        if rtl:                       # reportlab بيرتّب الأعمدة من الشمال - فنعكس عشان أول عمود يكون على اليمين
            cols = list(reversed(cols)); rows = [list(reversed(r)) for r in rows]
        n = len(cols)
        weights = []
        for i in range(n):
            ln = max([len(cols[i])] + [len(r[i]) for r in rows[:300]])
            weights.append(min(40, max(5, ln)))
        tot = sum(weights)
        widths = [width * w / tot for w in weights]
        body = [[P(c, st_head) for c in cols]] + [[P(v, st_norm) for v in r] for r in rows]
        tb = Table(body, colWidths=widths, repeatRows=1)
        tb.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A7A5E')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
                                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')]),
                                ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3), ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        if t['caption'] and t['caption'] != title:
            story.append(P(t['caption'], st_cap)); story.append(Spacer(1, 3))
        story += [tb, Spacer(1, 12)]

    def footer(canvas, doc):
        canvas.saveState(); canvas.setFont(font, 8); canvas.setFillColor(colors.HexColor('#6B7280'))
        canvas.drawCentredString(size[0] / 2, 14, shape(f'صفحة {doc.page}' if rtl else f'Page {doc.page}'))
        canvas.restoreState()
    doc = SimpleDocTemplate(path, pagesize=size, rightMargin=margin, leftMargin=margin, topMargin=24, bottomMargin=30, title=title)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def print_control(root, title, out_dir, rtl=True, subtitle=''):
    """يطلّع PDF للشاشة/النافذة (root) ويرجّع مساره."""
    data = extract(root)
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    return build_pdf(data, title, os.path.join(out_dir, f'screen_{stamp}.pdf'), rtl=rtl, subtitle=subtitle)


PREVIEW_MAX_ROWS = 200


def open_preview(page, root, title, subtitle='', rtl=True, out_dir=None, on_print=None):
    """نافذة معاينة قبل الطباعة: نفس محتوى الـ PDF (العنوان، الفلاتر، الأرقام، الجداول) بتتعرض في نافذة وفيها زر طباعة (PDF) وإغلاق."""
    data = extract(root)
    from . import theme
    mx = 0
    body = []
    if data['filters']:
        body.append(ft.Text(' | '.join(f'{k}: {v}' for k, v in data['filters']), size=12, color=theme.TEXT_MUTED))
    if data['stats']:
        body.append(ft.Row([ft.Container(ft.Column([ft.Text(k, size=11, color=theme.TEXT_MUTED), ft.Text(v, size=15, weight=ft.FontWeight.W_700)], spacing=1),
                                         padding=8, border=ft.border.Border(top=ft.border.BorderSide(1, theme.BORDER_LIGHT), bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT), left=ft.border.BorderSide(1, theme.BORDER_LIGHT), right=ft.border.BorderSide(1, theme.BORDER_LIGHT)), border_radius=8) for k, v in data['stats']], wrap=True, spacing=8, run_spacing=8))
    if not data['tables']:
        body.append(ft.Text('لا توجد جداول في الشاشة دي للطباعة', size=13))
    for t in data['tables']:
        mx = max(mx, len(t['columns']))
        if t['caption'] and t['caption'] != title:
            body.append(ft.Text(t['caption'], size=14, weight=ft.FontWeight.W_700, color=theme.PRIMARY))
        rows = t['rows'][:PREVIEW_MAX_ROWS]
        dt = ft.DataTable(columns=[ft.DataColumn(ft.Text(c, size=12, weight=ft.FontWeight.W_700)) for c in t['columns']],
                          rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(v, size=12)) for v in r]) for r in rows],
                          heading_row_height=36, data_row_min_height=32, data_row_max_height=44, column_spacing=16)
        body.append(ft.Row([dt], scroll=ft.ScrollMode.AUTO))
        if len(t['rows']) > len(rows):
            body.append(ft.Text(f'المعاينة بتعرض أول {len(rows)} صف من {len(t["rows"])} - الطباعة (PDF) فيها كل الصفوف', size=11, color=theme.TEXT_MUTED))
    dlg = ft.AlertDialog(modal=True, title=ft.Text(title + (f' - {subtitle}' if subtitle else '')),
                         content=ft.Container(ft.Column(body, spacing=10, scroll=ft.ScrollMode.AUTO, tight=False), width=min(1100, max(360, int(page.width or 900) - 60)),
                                              height=min(560, max(300, int(page.height or 700) - 220))))

    def close(e=None):
        dlg.open = False; page.update()

    def do_print(e=None):
        try:
            if on_print:
                on_print()
            else:
                path = print_control(root, title, out_dir or os.getcwd(), rtl=rtl, subtitle=subtitle)
                theme.open_or_download_file(page, path)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذرت الطباعة: {ex}'), open=True)); page.update()

    dlg.actions = [ft.TextButton('إغلاق', on_click=close),
                   ft.ElevatedButton('طباعة', icon=ft.Icons.PRINT_OUTLINED, on_click=do_print, bgcolor=theme.PRIMARY, color='#FFFFFF')]
    page.overlay.append(dlg); dlg.open = True; page.update()
    return dlg
