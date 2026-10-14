"""تجهيز شركة جديدة فاضية (بيتشغّل كعملية مستقلة بـ ERP_HOME الخاص بالشركة):
   echo '{"company":..,"owner":..,"phone":..,"admin_password":..,"expires":"YYYY-MM-DD"}' | python -m erp_app.provision
بيعمل القاعدة (جداول + بيانات أساسية فاضية)، يضبط كلمة مرور المدير واسم الشركة، ويكتب trial.json."""
import datetime
import json
import sys


def main():
    a = json.load(sys.stdin)
    from . import services, trial
    from .db import init_db
    init_db()
    services.set_current_user(None)
    pw = a["admin_password"]
    services.check_password_policy(pw, "admin")
    from .db import User, get_session
    with get_session() as s:
        u = s.query(User).filter(User.username == "admin").first()
        u.password_hash = services._hash_password(pw)
        u.full_name = (a.get("owner") or "مدير النظام")[:150]
        s.commit()
    services.update_company_settings(name=a["company"], phone=a.get("phone", ""))
    trial.write(datetime.date.fromisoformat(a["expires"]), company=a["company"], owner=a.get("owner", ""), phone=a.get("phone", ""),
                **{k: a[k] for k in ("plan", "plan_label", "paid", "max_users", "max_branches") if k in a})
    print("OK")


if __name__ == "__main__":
    main()
