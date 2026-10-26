"""فحص ثابت: مفيش أسماء غير معرّفة (NameError كامن) في كل ملفات البرنامج. بيمنع رجوع أخطاء زي inventory_count_report."""
import io
import pathlib

from pyflakes import api, reporter

ROOT = pathlib.Path(__file__).resolve().parent.parent / "erp_app"


def test_no_undefined_names_in_service_modules():
    bad = []
    for f in [*sorted(ROOT.rglob("*.py")), ROOT.parent / "main.py"]:
        out = io.StringIO()
        api.check(f.read_text(encoding="utf-8"), f.name, reporter.Reporter(out, out))
        bad += [l for l in out.getvalue().splitlines() if "undefined name" in l]
    assert not bad, "\n".join(bad[:20])


def test_inventory_count_report_runs(S):
    assert isinstance(S.inventory_count_report(), list)
