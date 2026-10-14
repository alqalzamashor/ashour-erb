import flet as ft
from .. import services, theme


def build_settings(page: ft.Page):
    settings = services.get_company_settings()

    name = ft.TextField(label="اسم الشركة", value=settings.name or "")
    vat = ft.TextField(label="الرقم الضريبي (VAT)", value=settings.vat_number or "")
    phone = ft.TextField(label="الهاتف", value=settings.phone or "")
    address = ft.TextField(label="العنوان", value=settings.address or "",
                            multiline=True, min_lines=2, max_lines=3)
    tax_rate = ft.TextField(label="نسبة الضريبة الافتراضية %", value=str(settings.default_tax_rate or 15),
                             keyboard_type=ft.KeyboardType.NUMBER)
    prefix_sales = ft.TextField(label="بادئة رقم فاتورة المبيعات", value=settings.invoice_prefix_sales or "S-", width=200)
    prefix_purch = ft.TextField(label="بادئة رقم فاتورة المشتريات", value=settings.invoice_prefix_purchase or "P-", width=200)
    annual_leave = ft.TextField(label="رصيد الإجازة السنوية (أيام لكل موظف)", value=str(settings.annual_leave_days or 21), width=240, keyboard_type=ft.KeyboardType.NUMBER)
    logo_path = ft.TextField(label="مسار شعار الشركة (PNG/JPG)", value=settings.logo_path or "", hint_text=r"مثال: C:\ERP\logo.png", expand=True)

    zatca_switch = ft.Switch(label="تفعيل الإرسال المباشر لمنصة فاتورة (ZATCA)", value=bool(settings.zatca_enabled))
    zatca_env = ft.Dropdown(
        label="البيئة", width=180,
        options=[ft.dropdown.Option('sandbox', 'تجريبية (Sandbox)'), ft.dropdown.Option('production', 'فعلية (Production)')],
        value=settings.zatca_environment or 'sandbox',
    )
    zatca_url = ft.TextField(label="رابط منصة فاتورة (API URL)", value=settings.zatca_api_url or "", expand=True,
                              hint_text="مثال: https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal")
    zatca_user = ft.TextField(label="اسم المستخدم / CSID", value=settings.zatca_username or "", width=260)
    zatca_pass = ft.TextField(label="كلمة المرور / Secret", value=settings.zatca_password or "", width=260, password=True, can_reveal_password=True)
    zatca_note = ft.Text(
        "تنبيه: الخاصية دي بتحاول إرسال بيانات الفاتورة لمنصة فاتورة، لكن الربط الكامل (المرحلة الثانية) "
        "بيحتاج شهادة CSID حقيقية مسجّلة رسمياً مع الهيئة وملف XML موقّع - من غيرها هيوصلك خطأ واضح من المنصة نفسها "
        "بدل ما تفشل الفاتورة بصمت. الـ QR (المرحلة الأولى) بيشتغل ويظهر على الفاتورة في كل الأحوال بغض النظر عن الإعداد ده.",
        color=theme.TEXT_MUTED, size=12,
    )

    status = ft.Text("", color=theme.SUCCESS, visible=False)

    def save(e):
        try:
            services.update_company_settings(
                name=(name.value or "").strip() or "اسم الشركة",
                vat_number=(vat.value or "").strip(),
                phone=(phone.value or "").strip(),
                address=(address.value or "").strip(),
                default_tax_rate=float(tax_rate.value or 15),
                invoice_prefix_sales=(prefix_sales.value or "S-").strip(),
                invoice_prefix_purchase=(prefix_purch.value or "P-").strip(),
                annual_leave_days=int(annual_leave.value or 21),
                logo_path=(logo_path.value or "").strip(),
                zatca_enabled=zatca_switch.value,
                zatca_environment=zatca_env.value,
                zatca_api_url=(zatca_url.value or "").strip(),
                zatca_username=(zatca_user.value or "").strip(),
                zatca_password=zatca_pass.value or "",
            )
            status.value = "تم حفظ الإعدادات بنجاح"
            status.color = theme.SUCCESS
            status.visible = True
        except Exception as ex:
            status.value = str(ex)
            status.color = theme.DANGER
            status.visible = True
        page.update()

    form = theme.card(
        ft.Column(
            [
                ft.Text("بيانات الشركة", size=16, weight=ft.FontWeight.BOLD),
                ft.Text("هذه البيانات تظهر في الفواتير وتستخدم في QR الزكاة السعودية.",
                        color=theme.TEXT_MUTED, size=12),
                ft.Container(height=6),
                name, vat, phone, address,
                ft.Row([tax_rate, prefix_sales, prefix_purch, annual_leave], wrap=True, spacing=12),
                ft.Row([logo_path], expand=True),
                ft.Text("ضع مسار ملف الشعار في الجهاز. سيظهر تلقائياً في تقارير PDF وExcel الرسمية.", color=theme.TEXT_MUTED, size=12),
                ft.Row([
                    ft.FilledButton("حفظ", icon=ft.Icons.SAVE_OUTLINED,
                                    bgcolor=theme.PRIMARY, on_click=save),
                    status,
                ], spacing=16),
            ],
            spacing=12,
        ),
    )

    zatca_form = theme.card(
        ft.Column(
            [
                ft.Text("الربط مع منصة فاتورة (ZATCA)", size=16, weight=ft.FontWeight.BOLD),
                zatca_note,
                ft.Container(height=6),
                ft.Row([zatca_switch, zatca_env], wrap=True, spacing=20),
                zatca_url,
                ft.Row([zatca_user, zatca_pass], wrap=True, spacing=12),
            ],
            spacing=12,
        ),
    )

    smtp_host = ft.TextField(label="خادم SMTP", value=settings.smtp_host or "", width=260, hint_text="مثال: smtp.gmail.com")
    smtp_port = ft.TextField(label="المنفذ (Port)", value=str(settings.smtp_port or 587), width=110, keyboard_type=ft.KeyboardType.NUMBER)
    smtp_tls = ft.Switch(label="استخدام TLS", value=bool(settings.smtp_use_tls if settings.smtp_use_tls is not None else True))
    smtp_username = ft.TextField(label="اسم المستخدم (البريد المرسل منه غالباً)", value=settings.smtp_username or "", width=280)
    smtp_password = ft.TextField(label="كلمة المرور / App Password", value=settings.smtp_password or "", width=260, password=True, can_reveal_password=True)
    smtp_from = ft.TextField(label="البريد الظاهر كمُرسِل", value=settings.smtp_from_email or "", width=280)
    smtp_status = ft.Text("", visible=False)

    def save_smtp(e):
        try:
            services.update_company_settings(
                smtp_host=(smtp_host.value or "").strip(),
                smtp_port=int(smtp_port.value or 587),
                smtp_use_tls=smtp_tls.value,
                smtp_username=(smtp_username.value or "").strip(),
                smtp_password=smtp_password.value or "",
                smtp_from_email=(smtp_from.value or "").strip(),
            )
            smtp_status.value = "تم حفظ إعدادات البريد بنجاح"
            smtp_status.color = theme.SUCCESS
            smtp_status.visible = True
        except Exception as ex:
            smtp_status.value = str(ex)
            smtp_status.color = theme.DANGER
            smtp_status.visible = True
        page.update()

    smtp_form = theme.card(
        ft.Column(
            [
                ft.Text("إرسال الفواتير بالبريد الإلكتروني (SMTP)", size=16, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "لو بتستخدم Gmail، محتاج تفعّل 'App Password' من إعدادات حساب Google بدل كلمة المرور العادية "
                    "(Google بتمنع تسجيل الدخول العادي من برامج خارجية لأسباب أمنية).",
                    color=theme.TEXT_MUTED, size=12,
                ),
                ft.Container(height=6),
                ft.Row([smtp_host, smtp_port, smtp_tls], wrap=True, spacing=16),
                ft.Row([smtp_username, smtp_password], wrap=True, spacing=12),
                smtp_from,
                ft.Row([ft.FilledButton("حفظ إعدادات البريد", icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save_smtp), smtp_status], spacing=16),
            ],
            spacing=12,
        ),
    )

    PAPER_SIZE_OPTIONS = [
        ("a4", "ورقة A4 عادية"), ("thermal80", "إيصال حراري 80مم"), ("thermal58", "إيصال حراري 58مم"),
    ]
    COLOR_OPTIONS = [
        ("#6C4EE3", "بنفسجي (افتراضي)"), ("#0EA5E9", "أزرق"), ("#16A34A", "أخضر"),
        ("#DC2626", "أحمر"), ("#D97706", "برتقالي"), ("#0F172A", "أسود"),
    ]
    print_paper = ft.Dropdown(label="حجم الورق", width=220, options=[ft.dropdown.Option(k, v) for k, v in PAPER_SIZE_OPTIONS], value=settings.print_paper_size or "a4")
    print_color = ft.Dropdown(label="لون المستندات", width=220, options=[ft.dropdown.Option(k, v) for k, v in COLOR_OPTIONS], value=settings.print_color or "#6C4EE3")
    print_font = ft.Dropdown(label="حجم الخط", width=160, options=[ft.dropdown.Option("normal", "عادي"), ft.dropdown.Option("large", "كبير")], value=settings.print_font_size or "normal")
    print_logo_switch = ft.Switch(label="إظهار الشعار", value=bool(settings.print_show_logo if settings.print_show_logo is not None else True))
    print_qr_switch = ft.Switch(label="إظهار QR الزكاة", value=bool(settings.print_show_qr if settings.print_show_qr is not None else True))
    print_footer = ft.TextField(label="ملاحظة تظهر أسفل كل مستند (اختياري)", value=settings.print_footer_note or "", width=420, hint_text="مثال: شكراً لتعاملكم معنا - سياسة الاستبدال خلال 7 أيام")
    print_status = ft.Text("", visible=False)

    def save_print(e):
        try:
            services.update_company_settings(
                print_paper_size=print_paper.value, print_color=print_color.value,
                print_font_size=print_font.value, print_show_logo=print_logo_switch.value,
                print_show_qr=print_qr_switch.value, print_footer_note=(print_footer.value or "").strip(),
            )
            print_status.value = "تم حفظ إعدادات الطباعة بنجاح"
            print_status.color = theme.SUCCESS
            print_status.visible = True
        except Exception as ex:
            print_status.value = str(ex)
            print_status.color = theme.DANGER
            print_status.visible = True
        page.update()

    def preview_print(e):
        try:
            import types
            preview_settings = types.SimpleNamespace(
                name=settings.name, vat_number=settings.vat_number, address=settings.address, phone=settings.phone,
                logo_path=settings.logo_path,
                print_paper_size=print_paper.value, print_color=print_color.value, print_font_size=print_font.value,
                print_show_logo=print_logo_switch.value, print_show_qr=print_qr_switch.value,
                print_footer_note=(print_footer.value or "").strip(),
            )
            from ..invoice_pdf import _simple_doc_pdf
            import os as _os
            exports_dir = services.downloads_dir()
            path = _simple_doc_pdf(
                "معاينة تنسيق الطباعة", settings.name or "",
                [("رقم تجريبي", "PREVIEW-001"), ("التاريخ", "2026-01-01"), ("الطرف", "عميل تجريبي"), ("المبلغ", "1,250.00")],
                exports_dir, "معاينة_تنسيق_الطباعة", footer_note=None, company=preview_settings,
            )
            theme.open_or_download_file(page, path)
            print_status.value = f"تم إنشاء معاينة وفتحها: {path}"
            print_status.color = theme.SUCCESS
            print_status.visible = True
        except Exception as ex:
            print_status.value = f"تعذرت المعاينة: {ex}"
            print_status.color = theme.DANGER
            print_status.visible = True
        page.update()

    print_form = theme.card(
        ft.Column(
            [
                ft.Text("تنسيق الطباعة", size=16, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "خصّص شكل كل المستندات المطبوعة (فواتير، سندات، قيود، إذون حركة) - حجم الورق (عادي أو إيصال "
                    "حراري لطابعات نقاط البيع)، اللون، حجم الخط، وملاحظة تذييل تظهر في آخر كل مستند.",
                    color=theme.TEXT_MUTED, size=12,
                ),
                ft.Container(height=6),
                ft.Row([print_paper, print_color, print_font], wrap=True, spacing=16),
                ft.Row([print_logo_switch, print_qr_switch], wrap=True, spacing=24),
                print_footer,
                ft.Row([
                    ft.FilledButton("حفظ إعدادات الطباعة", icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save_print),
                    ft.OutlinedButton("معاينة الشكل الآن", icon=ft.Icons.VISIBILITY_OUTLINED, on_click=preview_print),
                    print_status,
                ], wrap=True, spacing=16),
            ],
            spacing=12,
        ),
    )

    accounting_cfg = services.get_accounting_settings()
    all_postable_accounts = services.list_accounts(postable_only=True)
    acct_options = [(str(a.id), f"{a.code} - {a.name}") for a in all_postable_accounts]

    ACCOUNT_GROUPS = [
        ("الحسابات الأساسية", [
            ("receivable_account_id", "حساب العملاء الافتراضي"),
            ("payable_account_id", "حساب الموردين الافتراضي"),
            ("cash_account_id", "حساب النقدية الافتراضي"),
            ("retained_earnings_account_id", "حساب الأرباح المرحلة"),
        ]),
        ("المبيعات والمشتريات", [
            ("sales_account_id", "حساب إيرادات المبيعات"),
            ("purchases_account_id", "حساب المشتريات"),
            ("inventory_account_id", "حساب المخزون"),
            ("cogs_account_id", "حساب تكلفة البضاعة المباعة"),
            ("sales_discount_account_id", "حساب خصومات المبيعات الممنوحة"),
            ("purchase_discount_account_id", "حساب خصومات المشتريات المكتسبة"),
        ]),
        ("الضرائب", [
            ("vat_input_account_id", "ضريبة القيمة المضافة - مدخلات"),
            ("vat_output_account_id", "ضريبة القيمة المضافة - مخرجات"),
        ]),
        ("فروق الجرد", [
            ("inventory_gain_account_id", "حساب أرباح فروق الجرد"),
            ("inventory_loss_account_id", "حساب خسائر فروق الجرد"),
        ]),
        ("الرواتب والموظفين", [
            ("salary_expense_account_id", "حساب مصروف الرواتب"),
            ("salaries_payable_account_id", "حساب الرواتب مستحقة الدفع"),
            ("gosi_payable_account_id", "حساب التأمينات الاجتماعية مستحقة"),
            ("employee_advances_account_id", "حساب سلف الموظفين"),
            ("employee_custody_account_id", "حساب عهد الموظفين"),
            ("prepaid_expenses_account_id", "حساب المصروفات المدفوعة مقدمًا"),
        ]),
        ("الأصول الثابتة", [
            ("asset_loss_account_id", "حساب خسائر استبعاد الأصول (عجز الجرد)"),
        ]),
    ]

    accounting_fields = {}
    accounting_status = ft.Text("", visible=False)
    accounting_group_columns = []
    for group_title, group_fields in ACCOUNT_GROUPS:
        group_rows = []
        for field_key, field_label in group_fields:
            current_value = getattr(accounting_cfg, field_key, None)
            sd = theme.SearchableDropdown(label=field_label, width=340, options=acct_options, value=str(current_value) if current_value else None)
            accounting_fields[field_key] = sd
            group_rows.append(sd.control)
        accounting_group_columns.append(
            ft.Column([ft.Text(group_title, size=14, weight=ft.FontWeight.BOLD, color=theme.PRIMARY), ft.Row(group_rows, wrap=True, spacing=16)], spacing=8)
        )

    def save_accounting_links(e):
        try:
            updates = {key: (sd.value if sd.value else None) for key, sd in accounting_fields.items()}
            services.update_accounting_settings(**updates)
            accounting_status.value = "تم حفظ ربط الحسابات بنجاح"
            accounting_status.color = theme.SUCCESS
            accounting_status.visible = True
        except Exception as ex:
            accounting_status.value = str(ex)
            accounting_status.color = theme.DANGER
            accounting_status.visible = True
        page.update()

    accounting_form = theme.card(
        ft.Column(
            [
                ft.Text("ربط الحسابات المحاسبية الافتراضية", size=16, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "كل عملية تلقائية في البرنامج (فواتير، سندات، رواتب، فروق جرد...) محتاجة تعرف تسجّل على أي حساب من "
                    "شجرة حساباتك الخاصة. اربط كل حساب هنا حسب اختيارك - مش لازم تستخدم شجرة الحسابات الافتراضية اللي "
                    "جاية مع البرنامج، تقدر تبني شجرتك الخاصة بالكامل وتربطها هنا.",
                    color=theme.TEXT_MUTED, size=12,
                ),
                ft.Divider(),
                ft.Column(accounting_group_columns, spacing=16),
                ft.Row([ft.FilledButton("حفظ ربط الحسابات", icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save_accounting_links), accounting_status], spacing=16),
            ],
            spacing=12,
        )
    )

    from .. import scale_barcode
    sc_cfg = scale_barcode.get_config()
    sc_en = ft.Switch(label="تفعيل الباركود الموزون / المسعّر (EAN-13)", value=bool(sc_cfg["enabled"]))
    sc_prefix = ft.TextField(label="البادئة (أو أكتر بفاصلة)", width=160, dense=True, value=sc_cfg["prefix"])
    sc_plu = ft.TextField(label="أرقام كود الصنف", width=130, dense=True, value=str(sc_cfg["plu_len"]), keyboard_type=ft.KeyboardType.NUMBER)
    sc_val = ft.TextField(label="أرقام القيمة", width=120, dense=True, value=str(sc_cfg["value_len"]), keyboard_type=ft.KeyboardType.NUMBER)
    sc_kind = ft.Dropdown(label="القيمة داخل الباركود", width=170, value=sc_cfg["kind"], options=[ft.dropdown.Option("weight", "وزن"), ft.dropdown.Option("price", "سعر")])
    sc_wd = ft.TextField(label="قسمة الوزن (1000 = جرام→كجم)", width=230, dense=True, value=f"{sc_cfg['weight_divisor']:g}", keyboard_type=ft.KeyboardType.NUMBER)
    sc_pd = ft.TextField(label="قسمة السعر (100 = قروش→ريال)", width=230, dense=True, value=f"{sc_cfg['price_divisor']:g}", keyboard_type=ft.KeyboardType.NUMBER)
    sc_chk = ft.Switch(label="التحقق من رقم EAN-13 الأخير", value=bool(sc_cfg["check_digit"]))
    sc_status = ft.Text("", size=12, visible=False)

    def save_scale(e):
        try:
            scale_barcode.save_config(enabled=sc_en.value, prefix=sc_prefix.value, plu_len=sc_plu.value, value_len=sc_val.value, kind=sc_kind.value,
                                      weight_divisor=sc_wd.value, price_divisor=sc_pd.value, check_digit=sc_chk.value)
            sc_status.value = "تم الحفظ"; sc_status.color = theme.SUCCESS
        except Exception as ex:
            sc_status.value = str(ex); sc_status.color = theme.DANGER
        sc_status.visible = True
        page.update()

    scale_form = theme.card(ft.Column([
        ft.Text("الباركود الموزون / المسعّر (ميزان الخضار واللحوم)", size=16, weight=ft.FontWeight.BOLD),
        ft.Text("الشكل الافتراضي (13 رقم): 20 + كود الصنف (5 أرقام) + الوزن بالجرام (5 أرقام) + رقم تحقق. مثال: 2000123008509 = الصنف 123، وزن 0.850 كجم. سجّل كود الميزان كـ«باركود» لوحدة الصنف أو ككود الصنف (SKU).",
                size=11, color=theme.TEXT_MUTED),
        sc_en, ft.Row([sc_prefix, sc_plu, sc_val, sc_kind], wrap=True, spacing=12), ft.Row([sc_wd, sc_pd], wrap=True, spacing=12), sc_chk,
        ft.Row([ft.FilledButton("حفظ", icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save_scale), sc_status], spacing=12),
    ], spacing=10))

    return ft.Column(
        [theme.page_title("الإعدادات", "بيانات الشركة والفواتير والربط مع الزكاة والبريد الإلكتروني وتنسيق الطباعة وربط الحسابات"),
         ft.Container(height=12), form, ft.Container(height=16), zatca_form, ft.Container(height=16), smtp_form,
         ft.Container(height=16), print_form, ft.Container(height=16), scale_form, ft.Container(height=16), accounting_form],
        expand=True, scroll=ft.ScrollMode.AUTO,
    )
