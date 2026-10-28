from .financial_statements import build_ifrs_statements


def build_financial_consolidation(page):
    """القوائم المالية الموحدة والفروع بصيغة IFRS: عمود لكل فرع + الإجمالي الموحد، شجرة الحسابات، مقارنة بالفترة السابقة."""
    return build_ifrs_statements(page, by_branch=True, title='القوائم المالية الموحدة والفروع (IFRS)',
                                 subtitle='مركز مالي، ربح أو خسارة، تدفقات نقدية، حقوق ملكية، ومراكز التكلفة - بأعمدة الفروع والإجمالي الموحد')
