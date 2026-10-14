"""
توليد فاتورة ضريبية PDF كاملة (رأسية، بنود، إجماليات، QR) - قابلة للطباعة
أو الإرسال بالإيميل. بتستخدم نفس أسلوب اكتشاف الخط (نظام التشغيل) المستخدم
في report_export.py عشان تفضل متّسقة مع باقي المستندات في النظام.
"""
import os
import base64
import datetime

FONT_CANDIDATES = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    'C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/tahoma.ttf', 'C:/Windows/Fonts/segoeui.ttf',
]
FONT_CANDIDATES_BOLD = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    'C:/Windows/Fonts/arialbd.ttf', 'C:/Windows/Fonts/tahomabd.ttf', 'C:/Windows/Fonts/segoeuib.ttf',
]


def _shape_ar(text):
    text = str(text)
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _simple_doc_pdf(title, subtitle, rows, output_dir, filename, footer_note=None, company=None):
    """مستند PDF بسيط (سند / إذن حركة) - عنوان + جدول صف=تسمية/قيمة.
    بيقرأ إعدادات تنسيق الطباعة (حجم الورق/اللون/حجم الخط) من company لو
    اتبعتت، وإلا بيستخدم القيم الافتراضية."""
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{filename}.pdf")

    page_size, is_thermal = _paper_size(company)
    accent = getattr(company, 'print_color', None) or '#1A7A5E' if company else '#1A7A5E'
    is_large = (getattr(company, 'print_font_size', 'normal') if company else 'normal') == 'large'
    company_footer_note = getattr(company, 'print_footer_note', '') if company else ''
    base_size = (10 if is_large else 8) if is_thermal else (12 if is_large else 10)
    margin = 8 if is_thermal else 30
    value_w = (page_size[0] - 2*margin) * 0.62
    label_w = (page_size[0] - 2*margin) * 0.38

    font_reg = next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)
    font_name = 'ERPFont2'
    if font_reg:
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_reg))
        except Exception:
            font_name = 'Helvetica'
    else:
        font_name = 'Helvetica'

    title_style = ParagraphStyle('T', fontName=font_name, fontSize=base_size+6, alignment=TA_CENTER, leading=base_size+10)
    sub_style = ParagraphStyle('S', fontName=font_name, fontSize=base_size-2, alignment=TA_CENTER, textColor=colors.grey)
    label_style = ParagraphStyle('L', fontName=font_name, fontSize=base_size, alignment=TA_RIGHT)
    value_style = ParagraphStyle('V', fontName=font_name, fontSize=base_size, alignment=TA_RIGHT)

    doc = SimpleDocTemplate(path, pagesize=page_size, rightMargin=margin, leftMargin=margin, topMargin=margin, bottomMargin=margin)
    story = [Paragraph(_shape_ar(title), title_style)]
    if subtitle:
        story.append(Paragraph(_shape_ar(subtitle), sub_style))
    story.append(Spacer(1, 14))

    table_rows = [[Paragraph(_shape_ar(str(v)), value_style), Paragraph(_shape_ar(str(k)), label_style)] for k, v in rows]
    t = Table(table_rows, colWidths=[value_w, label_w], hAlign='RIGHT')
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D7D7E0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4 if is_thermal else 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 4 if is_thermal else 6),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F6FAF8')]),
    ]))
    story.append(t)
    combined_note = footer_note or company_footer_note
    if combined_note:
        story.append(Spacer(1, 16))
        story.append(Paragraph(_shape_ar(combined_note), sub_style))
    doc.build(story)
    return path


def _paper_size(company):
    """يرجّع (page_size, is_thermal) حسب إعداد حجم الورق المحفوظ."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    size = getattr(company, 'print_paper_size', 'a4') if company else 'a4'
    if size == 'thermal80':
        return (80 * mm, 2970 * mm), True
    if size == 'thermal58':
        return (58 * mm, 2970 * mm), True
    return A4, False


def generate_journal_entry_pdf(entry, company, output_dir):
    """
    قيد يومية بتصميم محاسبي احترافي: شعار + بيانات الشركة + رأسية القيد +
    جدول (حساب / بيان / مدين / دائن) بإجمالي، وخانات توقيع (إعداد/مراجعة/
    اعتماد) - بيحترم نفس إعدادات تنسيق الطباعة (حجم الورق/اللون/الخط/
    الشعار) المحفوظة في الإعدادات.
    entry: JournalEntry (مع .lines محمّلة، كل سطر معاه .account)
    يرجّع مسار الملف الناتج.
    """
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{entry.number}.pdf")

    page_size, is_thermal = _paper_size(company)
    accent = getattr(company, 'print_color', None) or '#1A7A5E' if company else '#1A7A5E'
    show_logo = getattr(company, 'print_show_logo', True) if company else True
    is_large = (getattr(company, 'print_font_size', 'normal') if company else 'normal') == 'large'
    footer_note = getattr(company, 'print_footer_note', '') if company else ''

    base_size, title_size, margin = (12 if is_large else 9), (21 if is_large else 18), (8 if is_thermal else 28)
    usable = page_size[0] - 2 * margin
    if is_thermal:
        col_widths = [usable * 0.42, usable * 0.29, usable * 0.29]  # بيان / مدين / دائن (بدون عمود كود منفصل لضيق المساحة)
    else:
        col_widths = [usable * 0.16, usable * 0.36, usable * 0.24, usable * 0.24]

    font_reg = next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)
    font_bold = next((f for f in FONT_CANDIDATES_BOLD if os.path.exists(f)), None)
    font_name, font_name_bold = 'ERPFont3', 'ERPFontBold3'
    if font_reg:
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_reg))
        except Exception:
            font_name = 'Helvetica'
    else:
        font_name = 'Helvetica'
    if font_bold:
        try:
            pdfmetrics.registerFont(TTFont(font_name_bold, font_bold))
        except Exception:
            font_name_bold = font_name
    else:
        font_name_bold = font_name

    title_style = ParagraphStyle('JTitle', fontName=font_name_bold, fontSize=title_size, alignment=TA_CENTER, leading=title_size + 4)
    sub_style = ParagraphStyle('JSub', fontName=font_name, fontSize=base_size - 2, alignment=TA_CENTER, textColor=colors.grey, leading=base_size + 2)
    normal_r = ParagraphStyle('JNormalR', fontName=font_name, fontSize=base_size, alignment=TA_RIGHT, leading=base_size + 3)
    bold_r = ParagraphStyle('JBoldR', fontName=font_name_bold, fontSize=base_size, alignment=TA_RIGHT, leading=base_size + 3)
    header_cell = ParagraphStyle('JHeaderCell', fontName=font_name_bold, fontSize=base_size - 1, alignment=TA_CENTER, textColor=colors.white)
    cell_r = ParagraphStyle('JCellR', fontName=font_name, fontSize=base_size - 1, alignment=TA_RIGHT, leading=base_size + 2)
    cell_c = ParagraphStyle('JCellC', fontName=font_name, fontSize=base_size - 1, alignment=TA_CENTER, leading=base_size + 2)
    sign_style = ParagraphStyle('JSign', fontName=font_name, fontSize=base_size - 1, alignment=TA_CENTER)

    doc = SimpleDocTemplate(path, pagesize=page_size, rightMargin=margin, leftMargin=margin, topMargin=margin, bottomMargin=margin)
    story = []

    logo = getattr(company, 'logo_path', None) if company else None
    if show_logo and logo and os.path.exists(logo):
        try:
            img = RLImage(logo)
            img._restrictSize(90 if is_thermal else 110, 50 if is_thermal else 60)
            story.append(img)
            story.append(Spacer(1, 4))
        except Exception:
            pass

    story.append(Paragraph(_shape_ar(company.name if company else 'اسم الشركة'), title_style))
    meta_line = ' | '.join(x for x in [
        f"الرقم الضريبي: {company.vat_number}" if company and getattr(company, 'vat_number', None) else None,
        getattr(company, 'phone', None) if company else None,
    ] if x)
    if meta_line:
        story.append(Paragraph(_shape_ar(meta_line), sub_style))
    story.append(Spacer(1, 10))

    story.append(Paragraph(_shape_ar('قيد يومية'), ParagraphStyle('JType', fontName=font_name_bold, fontSize=base_size + 3, alignment=TA_CENTER)))
    story.append(Spacer(1, 8))

    status_label = 'مرحّل' if entry.posted else 'مسودة'
    info_rows = [
        [Paragraph(_shape_ar(entry.number), bold_r), Paragraph(_shape_ar('رقم القيد'), normal_r)],
        [Paragraph(_shape_ar(entry.date.strftime('%Y-%m-%d')), normal_r), Paragraph(_shape_ar('التاريخ'), normal_r)],
        [Paragraph(_shape_ar(entry.reference or '-'), normal_r), Paragraph(_shape_ar('المرجع'), normal_r)],
        [Paragraph(_shape_ar(status_label), normal_r), Paragraph(_shape_ar('الحالة'), normal_r)],
    ]
    if entry.description:
        info_rows.append([Paragraph(_shape_ar(entry.description), normal_r), Paragraph(_shape_ar('البيان'), normal_r)])
    info_w = [usable * 0.62, usable * 0.38]
    info_table = Table(info_rows, colWidths=info_w, hAlign='RIGHT')
    info_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    story.append(info_table)
    story.append(Spacer(1, 10))

    if is_thermal:
        header_row = [Paragraph(_shape_ar('دائن'), header_cell), Paragraph(_shape_ar('مدين'), header_cell), Paragraph(_shape_ar('الحساب / البيان'), header_cell)]
    else:
        header_row = [Paragraph(_shape_ar('دائن'), header_cell), Paragraph(_shape_ar('مدين'), header_cell),
                      Paragraph(_shape_ar('البيان'), header_cell), Paragraph(_shape_ar('الحساب'), header_cell)]
    table_rows = [header_row]
    total_debit = total_credit = 0.0
    for ln in entry.lines:
        account_text = f"{ln.account.code} - {ln.account.name}" if ln.account else '-'
        line_desc = ln.description or ''
        total_debit += ln.debit or 0
        total_credit += ln.credit or 0
        if is_thermal:
            combined = account_text + (f" - {line_desc}" if line_desc else "")
            table_rows.append([
                Paragraph(f"{ln.credit:,.2f}" if ln.credit else "-", cell_c),
                Paragraph(f"{ln.debit:,.2f}" if ln.debit else "-", cell_c),
                Paragraph(_shape_ar(combined), cell_r),
            ])
        else:
            table_rows.append([
                Paragraph(f"{ln.credit:,.2f}" if ln.credit else "-", cell_c),
                Paragraph(f"{ln.debit:,.2f}" if ln.debit else "-", cell_c),
                Paragraph(_shape_ar(line_desc) if line_desc else "-", cell_r),
                Paragraph(_shape_ar(account_text), cell_r),
            ])
    # صف الإجمالي
    if is_thermal:
        table_rows.append([Paragraph(f"{total_credit:,.2f}", bold_r), Paragraph(f"{total_debit:,.2f}", bold_r), Paragraph(_shape_ar('الإجمالي'), bold_r)])
    else:
        table_rows.append([Paragraph(f"{total_credit:,.2f}", bold_r), Paragraph(f"{total_debit:,.2f}", bold_r), Paragraph('', normal_r), Paragraph(_shape_ar('الإجمالي'), bold_r)])

    lines_table = Table(table_rows, colWidths=col_widths, repeatRows=1, hAlign='RIGHT')
    lines_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(accent)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EDF3F0')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D7D7E0')),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor(accent)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3 if is_thermal else 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3 if is_thermal else 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F6FAF8')]),
    ]))
    story.append(lines_table)

    diff = abs(total_debit - total_credit)
    if diff > 0.01:
        story.append(Spacer(1, 6))
        story.append(Paragraph(_shape_ar(f'تنبيه: القيد غير متوازن - الفرق {diff:,.2f}'), ParagraphStyle('JWarn', fontName=font_name_bold, fontSize=base_size - 1, alignment=TA_CENTER, textColor=colors.red)))

    story.append(Spacer(1, 20 if is_thermal else 34))
    if not is_thermal:
        sign_table = Table(
            [[Paragraph(_shape_ar('اعتماد'), sign_style), Paragraph(_shape_ar('مراجعة'), sign_style), Paragraph(_shape_ar('إعداد'), sign_style)]],
            colWidths=[usable / 3] * 3, hAlign='RIGHT',
        )
        sign_table.setStyle(TableStyle([('LINEABOVE', (0, 0), (-1, 0), 0.6, colors.HexColor('#B9B7C6')), ('TOPPADDING', (0, 0), (-1, 0), 6)]))
        story.append(sign_table)

    if footer_note:
        story.append(Spacer(1, 14))
        story.append(Paragraph(_shape_ar(footer_note), sub_style))

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont(font_name, 6 if is_thermal else 7)
        canvas.drawCentredString(doc_.pagesize[0] / 2, 10 if is_thermal else 14,
                                  _shape_ar(f"تم الإصدار إلكترونياً - {(company.name if company else '')} - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def _invoice_context(company):
    """إعدادات الطباعة المشتركة (حجم الورق، الألوان، الخطوط، الأنماط) - بتتحسب مرة
    واحدة وتتستخدم لفاتورة واحدة أو لمجموعة فواتير في ملف واحد."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    page_size, is_thermal = _paper_size(company)
    ctx = {
        'page_size': page_size, 'is_thermal': is_thermal,
        'accent': getattr(company, 'print_color', None) or '#1A7A5E',
        'show_logo': getattr(company, 'print_show_logo', True) if company else True,
        'show_qr_setting': (getattr(company, 'print_show_qr', True) if company else True),
        'is_large': (getattr(company, 'print_font_size', 'normal') if company else 'normal') == 'large',
        'footer_note': getattr(company, 'print_footer_note', '') if company else '',
    }
    is_large = ctx['is_large']
    if is_thermal:
        base_size, title_size, margin = (10 if is_large else 8), (13 if is_large else 11), 8
        ctx['col_widths'] = [(page_size[0] - 2 * margin) * w for w in (0.34, 0.16, 0.16, 0.12, 0.22)]
        ctx['info_widths'] = [(page_size[0] - 2 * margin) * 0.55, (page_size[0] - 2 * margin) * 0.45]
        ctx['totals_widths'] = [(page_size[0] - 2 * margin) * 0.45, (page_size[0] - 2 * margin) * 0.55]
    else:
        base_size, title_size, margin = (12 if is_large else 9), (21 if is_large else 18), 28
        ctx['col_widths'] = [80, 70, 70, 55, 195]
        ctx['info_widths'] = [300, 150]
        ctx['totals_widths'] = [150, 300]
    ctx.update(base_size=base_size, title_size=title_size, margin=margin)

    font_reg = next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)
    font_bold = next((f for f in FONT_CANDIDATES_BOLD if os.path.exists(f)), None)
    font_name, font_name_bold = 'ERPFont', 'ERPFontBold'
    if font_reg:
        try: pdfmetrics.registerFont(TTFont(font_name, font_reg))
        except Exception: font_name = 'Helvetica'
    else:
        font_name = 'Helvetica'
    if font_bold:
        try: pdfmetrics.registerFont(TTFont(font_name_bold, font_bold))
        except Exception: font_name_bold = font_name
    else:
        font_name_bold = font_name
    ctx.update(font_name=font_name, font_name_bold=font_name_bold)
    ctx['title_style'] = ParagraphStyle('InvTitle', fontName=font_name_bold, fontSize=title_size, alignment=TA_CENTER, leading=title_size + 4)
    ctx['sub_style'] = ParagraphStyle('InvSub', fontName=font_name, fontSize=base_size - 2, alignment=TA_CENTER, textColor=colors.grey, leading=base_size + 2)
    ctx['normal_r'] = ParagraphStyle('InvNormalR', fontName=font_name, fontSize=base_size, alignment=TA_RIGHT, leading=base_size + 3)
    ctx['bold_r'] = ParagraphStyle('InvBoldR', fontName=font_name_bold, fontSize=base_size, alignment=TA_RIGHT, leading=base_size + 3)
    ctx['header_cell'] = ParagraphStyle('InvHeaderCell', fontName=font_name_bold, fontSize=base_size - 1, alignment=TA_CENTER, textColor=colors.white)
    ctx['cell_r'] = ParagraphStyle('InvCellR', fontName=font_name, fontSize=base_size - 1, alignment=TA_RIGHT, leading=base_size + 2)
    ctx['cell_c'] = ParagraphStyle('InvCellC', fontName=font_name, fontSize=base_size - 1, alignment=TA_CENTER, leading=base_size + 2)
    return ctx


def _invoice_story(ctx, invoice, company, qr_png_base64, output_dir, party, party_label, doc_title, temp_files, number_label='رقم الفاتورة', extra_info=None, terms=None, notes=None):
    """عناصر صفحة فاتورة واحدة (ReportLab flowables)."""
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    is_thermal, accent = ctx['is_thermal'], ctx['accent']
    base_size = ctx['base_size']
    normal_r, bold_r, header_cell, cell_r, cell_c = ctx['normal_r'], ctx['bold_r'], ctx['header_cell'], ctx['cell_r'], ctx['cell_c']
    font_name, font_name_bold = ctx['font_name'], ctx['font_name_bold']
    show_qr = ctx['show_qr_setting'] and bool(qr_png_base64)
    story = []

    logo = getattr(company, 'logo_path', None) if company else None
    if ctx['show_logo'] and logo and os.path.exists(logo):
        try:
            img = RLImage(logo)
            img._restrictSize(90 if is_thermal else 110, 50 if is_thermal else 60)
            story.append(img)
            story.append(Spacer(1, 4))
        except Exception:
            pass

    story.append(Paragraph(_shape_ar(company.name if company else 'اسم الشركة'), ctx['title_style']))
    meta_line = ' | '.join(x for x in [
        f"الرقم الضريبي: {company.vat_number}" if company and company.vat_number else None,
        company.phone if company and company.phone else None,
    ] if x)
    if meta_line:
        story.append(Paragraph(_shape_ar(meta_line), ctx['sub_style']))
    if company and company.address:
        story.append(Paragraph(_shape_ar(company.address), ctx['sub_style']))
    story.append(Spacer(1, 10))

    invoice_type = doc_title or ('فاتورة ضريبية مبسّطة' if getattr(invoice, 'is_pos', False) else 'فاتورة ضريبية')
    if getattr(invoice, 'voided', False):
        invoice_type += ' (ملغاة)'
    story.append(Paragraph(_shape_ar(invoice_type), ParagraphStyle('InvType', fontName=font_name_bold, fontSize=base_size + 3, alignment=TA_CENTER)))
    story.append(Spacer(1, 8))

    party = party if party is not None else getattr(invoice, 'customer', None)
    info_rows = [
        [Paragraph(_shape_ar(invoice.number), bold_r), Paragraph(_shape_ar(number_label), normal_r)],
        [Paragraph(_shape_ar(invoice.date.strftime('%Y-%m-%d %H:%M')), normal_r), Paragraph(_shape_ar('التاريخ'), normal_r)],
        [Paragraph(_shape_ar(party.name if party else '-'), normal_r), Paragraph(_shape_ar(party_label), normal_r)],
    ]
    if party and getattr(party, 'vat_number', None):
        info_rows.append([Paragraph(_shape_ar(party.vat_number), normal_r), Paragraph(_shape_ar(f'الرقم الضريبي لل{party_label}'), normal_r)])
    for lbl, val in (extra_info or []):
        info_rows.append([Paragraph(_shape_ar(str(val)), normal_r), Paragraph(_shape_ar(lbl), normal_r)])
    info_table = Table(info_rows, colWidths=ctx['info_widths'], hAlign='RIGHT')
    info_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    story.append(info_table)
    story.append(Spacer(1, 10))

    table_rows = [[Paragraph(_shape_ar('الإجمالي'), header_cell), Paragraph(_shape_ar('الضريبة'), header_cell),
                   Paragraph(_shape_ar('السعر'), header_cell), Paragraph(_shape_ar('الكمية'), header_cell),
                   Paragraph(_shape_ar('الصنف'), header_cell)]]
    for it in getattr(invoice, 'items', []):
        line_subtotal = max(0.0, it.quantity * it.unit_price - (getattr(it, 'discount', 0) or 0))   # بعد خصم السطر
        line_tax = line_subtotal * (it.tax_rate or 0) / 100.0
        table_rows.append([
            Paragraph(f"{line_subtotal + line_tax:,.2f}", cell_c), Paragraph(f"{line_tax:,.2f}", cell_c),
            Paragraph(f"{it.unit_price:,.2f}", cell_c), Paragraph(f"{it.quantity:g}", cell_c),
            Paragraph(_shape_ar(it.product.name if it.product else '-'), cell_r),
        ])
    items_table = Table(table_rows, colWidths=ctx['col_widths'], repeatRows=1, hAlign='RIGHT')
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(accent)),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D7D7E0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3 if is_thermal else 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3 if is_thermal else 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F6FAF8')]),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10))

    totals_rows = [
        [Paragraph(f"{invoice.subtotal:,.2f}", normal_r), Paragraph(_shape_ar('الإجمالي قبل الضريبة'), normal_r)],
        [Paragraph(f"{invoice.tax_total:,.2f}", normal_r), Paragraph(_shape_ar('ضريبة القيمة المضافة'), normal_r)],
    ]
    if getattr(invoice, 'discount', 0):
        totals_rows.append([Paragraph(f"{invoice.discount:,.2f}", normal_r), Paragraph(_shape_ar('الخصم'), normal_r)])
    totals_rows.append([Paragraph(f"{invoice.total:,.2f}", bold_r), Paragraph(_shape_ar('الإجمالي شامل الضريبة'), bold_r)])
    totals_table = Table(totals_rows, colWidths=ctx['totals_widths'], hAlign='RIGHT')
    totals_table.setStyle(TableStyle([('LINEABOVE', (0, -1), (-1, -1), 0.6, colors.HexColor(accent)), ('TOPPADDING', (0, -1), (-1, -1), 6)]))
    story.append(totals_table)
    story.append(Spacer(1, 14))

    if show_qr:
        qr_path = os.path.join(output_dir, f"_qr_{invoice.number}.png")
        with open(qr_path, 'wb') as f:
            f.write(base64.b64decode(qr_png_base64))
        temp_files.append(qr_path)
        qr_size = 26 * mm if is_thermal else 32 * mm
        qr_img = RLImage(qr_path, width=qr_size, height=qr_size)
        qr_img.hAlign = 'CENTER'
        story.append(qr_img)

    for title, body in (('ملاحظات', notes), ('الشروط والأحكام', terms)):
        if body and str(body).strip():
            story.append(Spacer(1, 6))
            story.append(Paragraph(_shape_ar(title), bold_r))
            for ln in str(body).strip().splitlines():
                if ln.strip():
                    story.append(Paragraph(_shape_ar(ln.strip()), normal_r))
    if ctx['footer_note']:
        story.append(Spacer(1, 8))
        story.append(Paragraph(_shape_ar(ctx['footer_note']), ParagraphStyle('FooterNote', fontName=font_name, fontSize=base_size - 1, alignment=TA_CENTER)))
    return story


def _summary_story(ctx, company, entries, title, subtitle):
    """صفحة كشف في أول ملف الطباعة الجماعية: قايمة الفواتير وإجمالياتها."""
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    base = ctx['base_size']; page_w = ctx['page_size'][0] - 2 * ctx['margin']
    story = [Paragraph(_shape_ar(company.name if company else 'اسم الشركة'), ctx['title_style']), Spacer(1, 6),
             Paragraph(_shape_ar(title), ParagraphStyle('SumT', fontName=ctx['font_name_bold'], fontSize=base + 5, alignment=TA_CENTER, leading=base + 9))]
    if subtitle:
        story.append(Paragraph(_shape_ar(subtitle), ctx['sub_style']))
    story.append(Spacer(1, 10))
    head = [Paragraph(_shape_ar(h), ctx['header_cell']) for h in ('الإجمالي', 'الضريبة', 'قبل الضريبة', 'الطرف', 'التاريخ', 'رقم الفاتورة', 'م')]
    rows = [head]
    t_sub = t_tax = t_tot = 0.0
    for i, en in enumerate(entries, 1):
        inv = en['invoice']; party = en.get('party') if en.get('party') is not None else getattr(inv, 'customer', None)
        sign = 1
        rows.append([Paragraph(f"{inv.total:,.2f}", ctx['cell_c']), Paragraph(f"{inv.tax_total:,.2f}", ctx['cell_c']), Paragraph(f"{inv.subtotal:,.2f}", ctx['cell_c']),
                     Paragraph(_shape_ar(party.name if party else '-'), ctx['cell_r']), Paragraph(inv.date.strftime('%Y-%m-%d'), ctx['cell_c']),
                     Paragraph(_shape_ar(inv.number), ctx['cell_c']), Paragraph(str(i), ctx['cell_c'])])
        t_sub += inv.subtotal or 0; t_tax += inv.tax_total or 0; t_tot += inv.total or 0
    rows.append([Paragraph(f"{t_tot:,.2f}", ctx['bold_r']), Paragraph(f"{t_tax:,.2f}", ctx['bold_r']), Paragraph(f"{t_sub:,.2f}", ctx['bold_r']),
                 Paragraph(_shape_ar(f'الإجمالي - {len(entries)} فاتورة'), ctx['bold_r']), '', '', ''])
    widths = [page_w * w for w in (0.15, 0.12, 0.15, 0.28, 0.12, 0.13, 0.05)]
    tbl = Table(rows, colWidths=widths, repeatRows=1, hAlign='RIGHT')
    tbl.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(ctx['accent'])), ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D7D7E0')),
                             ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F6FAF8')]),
                             ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EAF5F0')), ('SPAN', (3, -1), (-1, -1)),
                             ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    story.append(tbl)
    return story


def generate_invoices_pdf(entries, company, output_dir, filename=None, include_summary=False, summary_title='كشف الفواتير المطبوعة', summary_subtitle=''):
    """يطبع فاتورة أو مجموعة فواتير في ملف PDF واحد، كل فاتورة في صفحة مستقلة.
    entries: قايمة dicts: {invoice, qr (base64 اختياري), party (اختياري), party_label, doc_title}.
    include_summary: صفحة كشف بإجماليات الفواتير في أول الملف (للورق A4 بس).
    بيرجّع مسار الملف الناتج."""
    from reportlab.platypus import SimpleDocTemplate, PageBreak

    if not entries:
        raise ValueError("مفيش فواتير للطباعة")
    os.makedirs(output_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(output_dir, filename or f"invoices_{stamp}.pdf")
    ctx = _invoice_context(company)
    margin = ctx['margin']
    doc = SimpleDocTemplate(path, pagesize=ctx['page_size'], rightMargin=margin, leftMargin=margin, topMargin=margin, bottomMargin=margin + (6 if len(entries) > 1 else 0))
    story, temp_files = [], []
    batch = len(entries) > 1
    if batch and include_summary and not ctx['is_thermal']:
        story += _summary_story(ctx, company, entries, summary_title, summary_subtitle)
        story.append(PageBreak())
    for i, en in enumerate(entries):
        story += _invoice_story(ctx, en['invoice'], company, en.get('qr'), output_dir, en.get('party'), en.get('party_label', 'العميل'), en.get('doc_title'), temp_files,
                                number_label=en.get('number_label', 'رقم الفاتورة'), extra_info=en.get('extra_info'), terms=en.get('terms'), notes=en.get('notes'))
        if i < len(entries) - 1:
            story.append(PageBreak())

    def footer(canvas, docu):
        canvas.saveState()
        canvas.setFont(ctx['font_name'], 6 if ctx['is_thermal'] else 7)
        text = f"تم الإصدار إلكترونياً - {(company.name if company else '')} - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        canvas.drawCentredString(docu.pagesize[0] / 2, 10 if ctx['is_thermal'] else 14, _shape_ar(text))
        if batch:
            canvas.drawString(margin, 14 if not ctx['is_thermal'] else 10, f"{docu.page}")
        canvas.restoreState()

    try:
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
    finally:
        for tmp in temp_files:
            try:
                os.remove(tmp)
            except Exception:
                pass
    return path


def generate_invoice_pdf(invoice, company, qr_png_base64, output_dir, party=None, party_label='العميل', doc_title=None):
    """
    invoice: SalesInvoice أو PurchaseInvoice (مع .items محمّلين)
    company: CompanySettings (بيحدد تنسيق الطباعة: حجم الورق، اللون، إظهار
    اللوجو/QR، حجم الخط، ملاحظة التذييل - كلها قابلة للتخصيص من الإعدادات)
    qr_png_base64: صورة QR بصيغة base64 (اختياري - مفيش QR لفواتير المشتريات)
    party: العميل أو المورد (لو None، بيحاول ياخد invoice.customer تلقائياً للتوافق مع الاستخدام القديم)
    يرجّع مسار الملف الناتج.
    """
    return generate_invoices_pdf([{'invoice': invoice, 'qr': qr_png_base64, 'party': party, 'party_label': party_label, 'doc_title': doc_title}],
                                 company, output_dir, filename=f"{invoice.number}.pdf")


_ONES = ['', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة', 'ستة', 'سبعة', 'ثمانية', 'تسعة']
_TEENS = ['عشرة', 'أحد عشر', 'اثنا عشر', 'ثلاثة عشر', 'أربعة عشر', 'خمسة عشر', 'ستة عشر', 'سبعة عشر', 'ثمانية عشر', 'تسعة عشر']
_TENS = ['', '', 'عشرون', 'ثلاثون', 'أربعون', 'خمسون', 'ستون', 'سبعون', 'ثمانون', 'تسعون']
_HUNDREDS = ['', 'مائة', 'مئتان', 'ثلاثمائة', 'أربعمائة', 'خمسمائة', 'ستمائة', 'سبعمائة', 'ثمانمائة', 'تسعمائة']


def _three_digits_to_words(n):
    """يحوّل رقم من 1 لـ 999 لكلمات عربية."""
    if n == 0:
        return ''
    parts = []
    h, r = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if r:
        if r < 10:
            parts.append(_ONES[r])
        elif r < 20:
            parts.append(_TEENS[r - 10])
        else:
            tens, ones = divmod(r, 10)
            if ones:
                parts.append(f"{_ONES[ones]} و{_TENS[tens]}")
            else:
                parts.append(_TENS[tens])
    return ' و'.join(parts)


def amount_to_arabic_words(amount, currency='ريال', subunit='هللة'):
    """يحوّل مبلغ رقمي (زي 1250.75) لصيغة عربية مكتوبة (زي 'ألف ومئتان وخمسون
    ريالاً وخمسة وسبعون هللة') - شائعة في السندات المحاسبية الرسمية."""
    amount = round(float(amount or 0), 2)
    whole = int(amount)
    fraction = int(round((amount - whole) * 100))

    def whole_to_words(n):
        if n == 0:
            return 'صفر'
        scale_names = ['', 'ألف', 'مليون', 'مليار']
        temp = n
        chunks = []
        while temp > 0:
            chunks.append(temp % 1000)
            temp //= 1000
        chunks = list(reversed(chunks))
        n_chunks = len(chunks)
        groups = []
        for i, chunk in enumerate(chunks):
            scale_idx = n_chunks - i - 1
            if chunk == 0:
                continue
            if scale_idx == 1:  # آلاف
                if chunk == 1:
                    groups.append('ألف')
                elif chunk == 2:
                    groups.append('ألفان')
                elif 3 <= chunk <= 10:
                    groups.append(f"{_three_digits_to_words(chunk)} آلاف")
                else:
                    groups.append(f"{_three_digits_to_words(chunk)} ألف")
            elif scale_idx == 0:
                groups.append(_three_digits_to_words(chunk))
            else:
                groups.append(f"{_three_digits_to_words(chunk)} {scale_names[scale_idx]}")
        return ' و'.join(groups)

    text = f"{whole_to_words(whole)} {currency}"
    if fraction:
        text += f" و{whole_to_words(fraction)} {subunit}"
    return f"{text} لا غير"


def generate_payment_pdf(payment, company, party_name, output_dir):
    """
    سند قبض/صرف بتصميم احترافي: شعار + رأسية + المبلغ بالأرقام والحروف +
    الطرف والحساب والسبب + خانات توقيع (المستلم/المحاسب/المدير المالي).
    payment: Payment (مع .account محمّل)
    party_name: اسم العميل/المورد/الطرف (نص جاهز)
    يرجّع مسار الملف الناتج.
    """
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{payment.number}.pdf")

    page_size, is_thermal = _paper_size(company)
    is_receipt = payment.payment_type == 'receipt'
    default_accent = '#16A34A' if is_receipt else '#DC2626'  # أخضر للقبض / أحمر للصرف كعرف محاسبي شائع
    accent = getattr(company, 'print_color', None) or default_accent if company else default_accent
    show_logo = getattr(company, 'print_show_logo', True) if company else True
    is_large = (getattr(company, 'print_font_size', 'normal') if company else 'normal') == 'large'
    footer_note = getattr(company, 'print_footer_note', '') if company else ''

    base_size, title_size, margin = (12 if is_large else 9), (21 if is_large else 18), (8 if is_thermal else 28)
    usable = page_size[0] - 2 * margin

    font_reg = next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)
    font_bold = next((f for f in FONT_CANDIDATES_BOLD if os.path.exists(f)), None)
    font_name, font_name_bold = 'ERPFont4', 'ERPFontBold4'
    if font_reg:
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_reg))
        except Exception:
            font_name = 'Helvetica'
    else:
        font_name = 'Helvetica'
    if font_bold:
        try:
            pdfmetrics.registerFont(TTFont(font_name_bold, font_bold))
        except Exception:
            font_name_bold = font_name
    else:
        font_name_bold = font_name

    title_style = ParagraphStyle('PTitle', fontName=font_name_bold, fontSize=title_size, alignment=TA_CENTER, leading=title_size + 4)
    sub_style = ParagraphStyle('PSub', fontName=font_name, fontSize=base_size - 2, alignment=TA_CENTER, textColor=colors.grey, leading=base_size + 2)
    normal_r = ParagraphStyle('PNormalR', fontName=font_name, fontSize=base_size, alignment=TA_RIGHT, leading=base_size + 4)
    bold_r = ParagraphStyle('PBoldR', fontName=font_name_bold, fontSize=base_size, alignment=TA_RIGHT, leading=base_size + 4)
    amount_style = ParagraphStyle('PAmount', fontName=font_name_bold, fontSize=base_size + 8, alignment=TA_CENTER, textColor=colors.HexColor(accent))
    words_style = ParagraphStyle('PWords', fontName=font_name, fontSize=base_size, alignment=TA_CENTER, leading=base_size + 6)
    sign_style = ParagraphStyle('PSign', fontName=font_name, fontSize=base_size - 1, alignment=TA_CENTER)

    doc = SimpleDocTemplate(path, pagesize=page_size, rightMargin=margin, leftMargin=margin, topMargin=margin, bottomMargin=margin)
    story = []

    logo = getattr(company, 'logo_path', None) if company else None
    if show_logo and logo and os.path.exists(logo):
        try:
            img = RLImage(logo)
            img._restrictSize(90 if is_thermal else 110, 50 if is_thermal else 60)
            story.append(img)
            story.append(Spacer(1, 4))
        except Exception:
            pass

    story.append(Paragraph(_shape_ar(company.name if company else 'اسم الشركة'), title_style))
    story.append(Spacer(1, 10))

    voucher_title = 'سند قبض' if is_receipt else 'سند صرف'
    title_box = Table([[Paragraph(_shape_ar(voucher_title), ParagraphStyle('VType', fontName=font_name_bold, fontSize=base_size + 5, alignment=TA_CENTER, textColor=colors.white))]],
                       colWidths=[usable], hAlign='RIGHT')
    title_box.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(accent)), ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    story.append(title_box)
    story.append(Spacer(1, 12))

    party_label = 'استلمنا من السيد/السادة' if is_receipt else 'صرف إلى السيد/السادة'
    info_rows = [
        [Paragraph(_shape_ar(payment.number), bold_r), Paragraph(_shape_ar('رقم السند'), normal_r)],
        [Paragraph(_shape_ar(payment.date.strftime('%Y-%m-%d')), normal_r), Paragraph(_shape_ar('التاريخ'), normal_r)],
        [Paragraph(_shape_ar(party_name or '-'), bold_r), Paragraph(_shape_ar(party_label), normal_r)],
        [Paragraph(_shape_ar(f"{payment.account.code} - {payment.account.name}") if payment.account else '-', normal_r), Paragraph(_shape_ar('الحساب'), normal_r)],
    ]
    if payment.reference:
        info_rows.append([Paragraph(_shape_ar(payment.reference), normal_r), Paragraph(_shape_ar('المرجع'), normal_r)])
    info_w = [usable * 0.62, usable * 0.38]
    info_table = Table(info_rows, colWidths=info_w, hAlign='RIGHT')
    info_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    story.append(info_table)
    story.append(Spacer(1, 14))

    amount_box = Table([[Paragraph(f"{payment.amount:,.2f}", amount_style)]], colWidths=[usable], hAlign='RIGHT')
    amount_box.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.2, colors.HexColor(accent)),
        ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(amount_box)
    story.append(Spacer(1, 8))

    words_text = f"فقط وقدره: {amount_to_arabic_words(payment.amount)}"
    story.append(Paragraph(_shape_ar(words_text), words_style))
    story.append(Spacer(1, 10))

    if payment.notes:
        story.append(Paragraph(_shape_ar(f"وذلك عن: {payment.notes}"), normal_r))
        story.append(Spacer(1, 10))

    if payment.voided:
        story.append(Paragraph(_shape_ar('** هذا السند ملغى **'), ParagraphStyle('VVoid', fontName=font_name_bold, fontSize=base_size + 2, alignment=TA_CENTER, textColor=colors.red)))
        story.append(Spacer(1, 10))

    story.append(Spacer(1, 20 if is_thermal else 36))
    if not is_thermal:
        sign_table = Table(
            [[Paragraph(_shape_ar('المدير المالي'), sign_style), Paragraph(_shape_ar('المحاسب'), sign_style), Paragraph(_shape_ar('المستلم / الاسم والتوقيع'), sign_style)]],
            colWidths=[usable / 3] * 3, hAlign='RIGHT',
        )
        sign_table.setStyle(TableStyle([('LINEABOVE', (0, 0), (-1, 0), 0.6, colors.HexColor('#B9B7C6')), ('TOPPADDING', (0, 0), (-1, 0), 6)]))
        story.append(sign_table)

    if footer_note:
        story.append(Spacer(1, 14))
        story.append(Paragraph(_shape_ar(footer_note), sub_style))

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont(font_name, 6 if is_thermal else 7)
        canvas.drawCentredString(doc_.pagesize[0] / 2, 10 if is_thermal else 14,
                                  _shape_ar(f"تم الإصدار إلكترونياً - {(company.name if company else '')} - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path
