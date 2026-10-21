"""لایهٔ قواعد قطعی — هشدارها اینجا ساخته می‌شوند، نه توسط مدل.

هر قاعده یک شناسه دارد تا در گزارش قابل ارجاع باشد.
"""
from __future__ import annotations

SEV = {"high": "بحرانی", "med": "هشدار", "low": "توجه", "info": "اطلاع"}


def _f(v, d=0):
    if v is None:
        return "—"
    return f"{v:,.{d}f}"


def evaluate(ctx, kpis: dict, branch: str = "مجتمع") -> list[dict]:
    out: list[dict] = []
    brs = [b for b in kpis if b != "مجتمع"]
    cm = "مجتمع"

    def k(b, code, key="act"):
        return (kpis.get(b, {}).get(code) or {}).get(key)

    # R01 — رشد هزینه از رشد درآمد پیشی گرفته
    gnet = k(cm, "FIN.GROW")
    rev_a, rev_l = k(cm, "FIN.REV", "act"), k(cm, "FIN.REV", "ly")
    cost_a, cost_l = k(cm, "FIN.COST", "act"), k(cm, "FIN.COST", "ly")
    if rev_l and cost_l:
        gr = (rev_a - rev_l) / abs(rev_l) * 100
        gc = (cost_a - cost_l) / abs(cost_l) * 100
        if gc > gr:
            out.append({
                "id": "R01", "severity": "high" if gc - gr > 10 else "med",
                "title": "رشد هزینه از رشد درآمد پیشی گرفته",
                "detail": f"درآمد {_f(gr,1)}٪ و هزینه {_f(gc,1)}٪ رشد کرده؛ شکاف {_f(gc-gr,1)} واحد درصد.",
                "kpi": ["FIN.REV", "FIN.COST"], "branch": "مجتمع",
            })

    # R02 — شعب زیان‌ده
    loss = [b for b in brs if (k(b, "FIN.NET") or 0) < 0]
    if loss:
        share = (k(cm, "WH.LOSS.AREA") or 0)
        out.append({
            "id": "R02", "severity": "high" if len(loss) >= 4 else "med",
            "title": f"{len(loss)} شعبه زیان‌ده",
            "detail": "، ".join(loss) + f" — این شعب {_f(share,1)}٪ فضای انبار مجتمع را در اختیار دارند.",
            "kpi": ["FIN.NET", "WH.LOSS.AREA"], "branch": "مجتمع",
        })

    # R03 — تحقق بودجهٔ هزینهٔ پرسنلی
    pb = k(cm, "PAY.BUD.ACHV")
    if pb is not None and pb > 105:
        out.append({
            "id": "R03", "severity": "high" if pb > 115 else "med",
            "title": "هزینهٔ پرسنلی از بودجه عبور کرده",
            "detail": f"تحقق {_f(pb,1)}٪ بودجه؛ مازاد {_f(k(cm,'PAY.TOT','act') - k(cm,'PAY.TOT','bud'))} میلیون ریال.",
            "kpi": ["PAY.BUD.ACHV", "PAY.TOT"], "branch": "مجتمع",
        })

    # R04 — اشغال انبار
    occ = k(cm, "WH.OCC")
    if occ is not None and occ < 35:
        out.append({
            "id": "R04", "severity": "med",
            "title": "ظرفیت انبار عمدتاً بلااستفاده است",
            "detail": f"اشغال {_f(occ,1)}٪؛ {_f(100-occ,1)}٪ ظرفیت خالی مانده است.",
            "kpi": ["WH.OCC"], "branch": "مجتمع",
        })
    over = [(b, k(b, "WH.OCC")) for b in brs if (k(b, "WH.OCC") or 0) > 100]
    if over:
        out.append({
            "id": "R11", "severity": "med",
            "title": "درصد اشغال بالای ۱۰۰٪ در چند شعبه — تناقض داده",
            "detail": "، ".join(f"{b} ({_f(v,1)}٪)" for b, v in over)
                      + " — فضای خالی منفی ثبت شده؛ ظرفیت یا فضای خالی این شعب بازبینی شود.",
            "kpi": ["WH.OCC"], "branch": "مجتمع",
        })
    for b in brs:
        o = k(b, "WH.OCC")
        if o is not None and 90 < o <= 100:
            out.append({
                "id": "R04b", "severity": "low",
                "title": f"انبار {b} اشباع است",
                "detail": f"اشغال {_f(o,1)}٪ — ریسک کمبود فضا برای بار جدید.",
                "kpi": ["WH.OCC"], "branch": b,
            })

    # R05 — جذب بودجهٔ پروژه
    ab = k(cm, "PRJ.ABSORB")
    if ab is not None and ab < 60:
        out.append({
            "id": "R05", "severity": "high" if ab < 45 else "med",
            "title": "اجرای پروژه‌ها عقب از برنامه است",
            "detail": f"جذب بودجه {_f(ab,1)}٪ و پیشرفت {_f(k(cm,'PRJ.PROG'),1)}٪ در نیمهٔ سال.",
            "kpi": ["PRJ.ABSORB", "PRJ.PROG"], "branch": "مجتمع",
        })

    # R06 — ناوگان کم‌بازده
    avg = k(cm, "FLT.TON.DEV")
    if avg:
        low = [(b, k(b, "FLT.TON.DEV")) for b in brs
               if (k(b, "FLT.OPS.BASE") or 0) and (k(b, "FLT.TON.DEV") or 0) < avg * 0.4]
        if low:
            out.append({
                "id": "R06", "severity": "med",
                "title": f"{len(low)} شعبه با بهره‌وری ناوگان زیر ۴۰٪ میانگین",
                "detail": "، ".join(f"{b} ({_f(v)} تن/دستگاه)" for b, v in low)
                          + f" — میانگین مجتمع {_f(avg)} تن.",
                "kpi": ["FLT.TON.DEV", "FLT.FEI"], "branch": "مجتمع",
            })

    # R07 — تمرکز عملیات
    conc = k(cm, "OPS.CONC")
    if conc is not None and conc > 65:
        out.append({
            "id": "R07", "severity": "med",
            "title": "تمرکز بالای عملیات در دو شعبه",
            "detail": f"{_f(conc,1)}٪ تناژ مجتمع در دو شعبه انجام می‌شود.",
            "kpi": ["OPS.CONC"], "branch": "مجتمع",
        })

    # R08 — انحراف شدید تناژ شعب
    for b in brs:
        t = k(b, "OPS.TON")
        if t is None:
            continue
    # R09 — سهم پیمانکاری
    cs = k(cm, "HR.CONTR.SHARE")
    if cs is not None and cs > 25:
        out.append({
            "id": "R09", "severity": "low",
            "title": "اتکای بالای نیروی انسانی به پیمانکاری",
            "detail": f"{_f(cs,1)}٪ پرسنل پیمانکاری هستند (دوره مشابه: {_f(k(cm,'HR.CONTR.SHARE','ly'),1)}٪).",
            "kpi": ["HR.CONTR.SHARE"], "branch": "مجتمع",
        })

    # R10 — نقص دادهٔ بودجه
    missing = [c for c in ("FIN.NET", "FIN.REV", "OPS.TON", "FLT.FUEL.BUD")
               if k(cm, c, "bud") is None]
    if missing:
        out.append({
            "id": "R10", "severity": "info",
            "title": "بودجه برای برخی شاخص‌ها وارد نشده",
            "detail": f"{len(missing)} شاخص ستون بودجه ندارد: " + "، ".join(missing)
                      + " — تا ورود قالب بودجه، مقایسه با بودجه نمایش داده نمی‌شود.",
            "kpi": missing, "branch": "مجتمع",
        })

    order = {"high": 0, "med": 1, "low": 2, "info": 3}
    out.sort(key=lambda a: order.get(a["severity"], 9))
    return out
