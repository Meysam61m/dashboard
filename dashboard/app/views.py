"""ساخت بستهٔ نمایش هر صفحه — بدون محاسبهٔ جدید؛ فقط خواندن شاخص‌های محاسبه‌شده."""
from __future__ import annotations

from . import catalog
from .config import PERIOD_LABEL
from .engine import Ctx, OPS_CODES, WH_CODES
from .rules import evaluate

C = {"navy": "#0E2A47", "teal": "#0E8F8F", "gold": "#C7A227", "red": "#C0392B",
     "green": "#1E8E5A", "purple": "#6B4C9A", "orange": "#D97706", "blue": "#2563A8",
     "grey": "#7A8C9E"}

PAGE_TITLES = {
    "overview": ("نمای مدیریتی", "Management Overview"),
    "fin": ("مالی و سودآوری", "Financial Performance"),
    "hr": ("نیروی انسانی", "Human Resources"),
    "pay": ("هزینهٔ پرسنلی", "Payroll Cost"),
    "wh": ("انبار و ظرفیت", "Warehouses"),
    "flt": ("ناوگان و بهره‌وری", "Fleet"),
    "ops": ("عملیات و تناژ", "Operations"),
    "prj": ("پروژه‌های سرمایه‌ای", "Projects"),
    "data": ("کیفیت داده", "Data Quality"),
}

DOMAIN_CARDS = {
    "fin": ["FIN.REV", "FIN.COST", "FIN.NET", "FIN.MARGIN"],
    "hr": ["HR.HEAD", "HR.TEMP.SHARE", "HR.CONTR.SHARE", "HR.BUD.ACHV"],
    "pay": ["PAY.TOT", "PAY.BUD.ACHV", "PAY.GROW", "PAY.PER.HEAD"],
    "wh": ["WH.COUNT", "WH.AREA", "WH.OCC", "WH.PROFIT.M2"],
    "flt": ["FLT.COUNT", "FLT.OPS.BASE", "FLT.TON.DEV", "FLT.COST.TON"],
    "ops": ["OPS.TON", "OPS.MOM", "OPS.TRANS.SHARE", "OPS.CONC"],
    "prj": ["PRJ.COUNT", "PRJ.PROG", "PRJ.ABSORB", "PRJ.OVERDUE"],
}


def load_kpis(conn, year: int, period: str) -> dict:
    out: dict[str, dict] = {}
    for r in conn.execute("SELECT * FROM kpi WHERE year=? AND period=?", (year, period)):
        out.setdefault(r["branch"], {})[r["code"]] = {
            "act": r["act"], "bud": r["bud"], "ly": r["ly"]}
    return out


def _meta(code):
    for row in catalog.KPI_CATALOG:
        if row[0] == code:
            return {"code": row[0], "title": row[1], "domain": row[2], "unit": row[3],
                    "direction": row[4], "formula": row[5], "decimals": row[6]}
    return {"code": code, "title": code, "domain": "", "unit": "", "direction": "flat",
            "formula": "", "decimals": 0}


def cards_for(kpis: dict, branch: str, codes: list[str]) -> list[dict]:
    row = kpis.get(branch, {})
    out = []
    for c in codes:
        v = row.get(c) or {"act": None, "bud": None, "ly": None}
        m = _meta(c)
        out.append({**m, "act": v["act"], "bud": v["bud"], "ly": v["ly"]})
    return out


def _series(kpis: dict, code: str, branches: list[str], key="act"):
    return [((kpis.get(b, {}).get(code) or {}).get(key)) for b in branches]


def build_page(conn, page: str, branch: str, year: int, period: str) -> dict:
    kpis = load_kpis(conn, year, period)
    ctx = Ctx(conn, year)
    alerts = evaluate(ctx, kpis, branch)
    brs = [b for b in kpis if b != "مجتمع"]
    plabel = f"{PERIOD_LABEL.get(period, period)} {year}"

    cards: list[dict] = []
    charts: list[dict] = []
    tables: list[dict] = []

    if page == "overview":
        cards = cards_for(kpis, branch, catalog.OVERVIEW_CARDS)
        monthly = ctx.monthly_ops("مجتمع")
        charts.append({
            "type": "line", "title": "روند ماهانه تناژ عملیات — شش‌ماهه نخست",
            "labels": ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور"],
            "series": [{"name": "تناژ عملیات (تن)", "values": monthly, "color": C["teal"]}],
            "unit": "تن", "decimals": 0,
        })
        order = sorted(brs, key=lambda b: -((kpis.get(b, {}).get("FIN.NET") or {}).get("act") or 0))
        charts.append({
            "type": "bar", "title": "سود خالص به تفکیک شعبه",
            "labels": order, "horizontal": True,
            "series": [{"name": "سود خالص (م.ریال)",
                        "values": _series(kpis, "FIN.NET", order),
                        "color": C["navy"],
                        "colors_by_sign": True}],
            "unit": "م.ریال", "decimals": 0,
        })
        tables.append({
            "title": "گزیدهٔ شاخص‌های کلیدی مجتمع",
            "columns": ["شاخص", "عملکرد", "بودجه", "دوره مشابه", "واحد"],
            "rows": [[_meta(c)["title"],
                      (kpis.get("مجتمع", {}).get(c) or {}).get("act"),
                      (kpis.get("مجتمع", {}).get(c) or {}).get("bud"),
                      (kpis.get("مجتمع", {}).get(c) or {}).get("ly"),
                      _meta(c)["unit"]]
                     for c in ["FIN.REV", "FIN.NET", "FIN.MARGIN", "OPS.TON", "PAY.TOT", "HR.HEAD"]],
            "numeric": [1, 2, 3], "decimals": [0, 0, 0],
        })

    elif page == "fin":
        cards = cards_for(kpis, branch, DOMAIN_CARDS["fin"])
        charts.append({
            "type": "bar", "title": "درآمد، هزینه و سود — مقایسه با دوره مشابه",
            "labels": ["درآمد", "هزینه", "سود"],
            "series": [{"name": "دوره جاری",
                        "values": [(kpis.get(branch, {}).get(c) or {}).get("act")
                                   for c in ("FIN.REV", "FIN.COST", "FIN.NET")],
                        "color": C["navy"]},
                       {"name": "دوره مشابه",
                        "values": [(kpis.get(branch, {}).get(c) or {}).get("ly")
                                   for c in ("FIN.REV", "FIN.COST", "FIN.NET")],
                        "color": C["grey"]}],
            "unit": "م.ریال", "decimals": 0,
        })
        order = sorted(brs, key=lambda b: -((kpis.get(b, {}).get("FIN.NET") or {}).get("act") or 0))
        charts.append({
            "type": "bar", "title": "سود خالص شعب — از سودده به زیان‌ده",
            "labels": order, "horizontal": True,
            "series": [{"name": "سود خالص (م.ریال)", "values": _series(kpis, "FIN.NET", order),
                        "color": C["teal"], "colors_by_sign": True}],
            "unit": "م.ریال", "decimals": 0,
        })
        tables.append({
            "title": "سود و زیان شعب",
            "columns": ["شعبه", "درآمد", "هزینه", "سود", "حاشیه (٪)"],
            "rows": [[b,
                      (kpis.get(b, {}).get("FIN.REV") or {}).get("act"),
                      (kpis.get(b, {}).get("FIN.COST") or {}).get("act"),
                      (kpis.get(b, {}).get("FIN.NET") or {}).get("act"),
                      (kpis.get(b, {}).get("FIN.MARGIN") or {}).get("act")]
                     for b in order],
            "numeric": [1, 2, 3, 4], "decimals": [0, 0, 0, 1],
        })

    elif page == "hr":
        cards = cards_for(kpis, branch, DOMAIN_CARDS["hr"])
        order = sorted(brs, key=lambda b: -((kpis.get(b, {}).get("HR.HEAD") or {}).get("act") or 0))
        charts.append({
            "type": "bar", "title": "تعداد پرسنل هر شعبه",
            "labels": order, "horizontal": True,
            "series": [{"name": "نفر", "values": _series(kpis, "HR.HEAD", order), "color": C["blue"]}],
            "unit": "نفر", "decimals": 0,
        })
        charts.append({
            "type": "bar", "title": "ترکیب قرارداد — عملکرد در برابر بودجه",
            "labels": ["موقت", "پیمانکاری"],
            "series": [
                {"name": "عملکرد", "values": [
                    (kpis.get(branch, {}).get("HR.TEMP.SHARE") or {}).get("act"),
                    (kpis.get(branch, {}).get("HR.CONTR.SHARE") or {}).get("act")], "color": C["teal"]},
                {"name": "دوره مشابه", "values": [
                    (kpis.get(branch, {}).get("HR.TEMP.SHARE") or {}).get("ly"),
                    (kpis.get(branch, {}).get("HR.CONTR.SHARE") or {}).get("ly")], "color": C["grey"]}],
            "unit": "%", "decimals": 1,
        })
        tables.append({
            "title": "نیروی انسانی شعب",
            "columns": ["شعبه", "کل پرسنل", "سهم موقت (٪)", "سهم پیمانکاری (٪)", "تحقق بودجه (٪)"],
            "rows": [[b,
                      (kpis.get(b, {}).get("HR.HEAD") or {}).get("act"),
                      (kpis.get(b, {}).get("HR.TEMP.SHARE") or {}).get("act"),
                      (kpis.get(b, {}).get("HR.CONTR.SHARE") or {}).get("act"),
                      (kpis.get(b, {}).get("HR.BUD.ACHV") or {}).get("act")]
                     for b in order],
            "numeric": [1, 2, 3, 4], "decimals": [0, 1, 1, 1],
        })

    elif page == "pay":
        cards = cards_for(kpis, branch, DOMAIN_CARDS["pay"])
        order = sorted([b for b in brs if (kpis.get(b, {}).get("PAY.PER.HEAD") or {}).get("act")],
                       key=lambda b: -((kpis.get(b, {}).get("PAY.PER.HEAD") or {}).get("act") or 0))
        charts.append({
            "type": "bar", "title": "سرانهٔ هزینهٔ پرسنلی هر شعبه",
            "labels": order, "horizontal": True,
            "series": [{"name": "م.ریال به ازای هر نفر",
                        "values": _series(kpis, "PAY.PER.HEAD", order), "color": C["orange"]}],
            "unit": "م.ریال", "decimals": 1,
        })
        charts.append({
            "type": "bar", "title": "هزینهٔ پرسنلی — عملکرد، بودجه و دوره مشابه",
            "labels": ["عملکرد", "بودجه", "دوره مشابه"],
            "series": [{"name": "م.ریال", "values": [
                (kpis.get(branch, {}).get("PAY.TOT") or {}).get("act"),
                (kpis.get(branch, {}).get("PAY.TOT") or {}).get("bud"),
                (kpis.get(branch, {}).get("PAY.TOT") or {}).get("ly")], "color": C["purple"]}],
            "unit": "م.ریال", "decimals": 0,
        })

    elif page == "wh":
        cards = cards_for(kpis, branch, DOMAIN_CARDS["wh"])
        order = sorted(brs, key=lambda b: -((kpis.get(b, {}).get("WH.OCC") or {}).get("act") or 0))
        charts.append({
            "type": "bar", "title": "درصد اشغال ظرفیت انبار — از پرترین به خالی‌ترین",
            "labels": order, "horizontal": True,
            "series": [{"name": "درصد اشغال", "values": _series(kpis, "WH.OCC", order),
                        "color": C["gold"], "threshold": 60}],
            "unit": "%", "decimals": 1,
        })
        types = []
        for t, fa in catalog.WH_TYPE_FA.items():
            area = ctx.sv(branch, [f"WH.AREA.{t}"])
            cap = ctx.sv(branch, [f"WH.CAP.{t}"])
            empty = ctx.sv(branch, [f"WH.EMPTY.{t}"])
            types.append({"name": fa, "area": area, "cap": cap,
                          "occ": (None if not cap else (cap - (empty or 0)) / cap * 100)})
        tables.append({
            "title": "ظرفیت به تفکیک نوع انبار",
            "columns": ["نوع انبار", "مساحت (م²)", "ظرفیت (تن)", "اشغال (٪)"],
            "rows": [[t["name"], t["area"], t["cap"], t["occ"]] for t in types],
            "numeric": [1, 2, 3], "decimals": [0, 0, 1],
        })
        order2 = sorted([b for b in brs if (kpis.get(b, {}).get("WH.PROFIT.M2") or {}).get("act") is not None],
                        key=lambda b: -((kpis.get(b, {}).get("WH.PROFIT.M2") or {}).get("act") or 0))
        charts.append({
            "type": "bar", "title": "سود به ازای هر متر مربع انبار",
            "labels": order2, "horizontal": True,
            "series": [{"name": "م.ریال بر م²", "values": _series(kpis, "WH.PROFIT.M2", order2),
                        "color": C["green"], "colors_by_sign": True}],
            "unit": "م.ریال", "decimals": 2,
        })

    elif page == "flt":
        cards = cards_for(kpis, branch, DOMAIN_CARDS["flt"])
        order = sorted([b for b in brs if (kpis.get(b, {}).get("FLT.OPS.BASE") or {}).get("act")],
                       key=lambda b: -((kpis.get(b, {}).get("FLT.TON.DEV") or {}).get("act") or 0))
        charts.append({
            "type": "bar", "title": "تن جابه‌جاشده به ازای هر دستگاه عملیاتی",
            "labels": order, "horizontal": True,
            "series": [{"name": "تن بر دستگاه", "values": _series(kpis, "FLT.TON.DEV", order),
                        "color": C["teal"]}],
            "unit": "تن", "decimals": 0,
        })
        groups = []
        for g in catalog.FLT_GROUPS:
            groups.append({"name": catalog.FLT_GROUP_FA[g], "value": ctx.s(branch, f"FLT.{g}")})
        charts.append({
            "type": "donut", "title": "ترکیب ناوگان",
            "labels": [g["name"] for g in groups],
            "series": [{"name": "دستگاه", "values": [g["value"] for g in groups],
                        "color": C["navy"]}],
            "unit": "دستگاه", "decimals": 0,
        })
        tables.append({
            "title": "بهره‌وری ناوگان شعب",
            "columns": ["شعبه", "دستگاه عملیاتی", "تن بر دستگاه", "شاخص کارایی"],
            "rows": [[b,
                      (kpis.get(b, {}).get("FLT.OPS.BASE") or {}).get("act"),
                      (kpis.get(b, {}).get("FLT.TON.DEV") or {}).get("act"),
                      (kpis.get(b, {}).get("FLT.FEI") or {}).get("act")]
                     for b in order],
            "numeric": [1, 2, 3], "decimals": [0, 0, 0],
        })

    elif page == "ops":
        cards = cards_for(kpis, branch, DOMAIN_CARDS["ops"])
        monthly = ctx.monthly_ops(branch if branch != "مجتمع" else "مجتمع")
        charts.append({
            "type": "line", "title": "روند ماهانه تناژ عملیات",
            "labels": ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور"],
            "series": [{"name": "تن", "values": monthly, "color": C["teal"]}],
            "unit": "تن", "decimals": 0,
        })
        order = sorted(brs, key=lambda b: -((kpis.get(b, {}).get("OPS.TON") or {}).get("act") or 0))
        charts.append({
            "type": "bar", "title": "تناژ عملیات شعب",
            "labels": order, "horizontal": True,
            "series": [{"name": "تن", "values": _series(kpis, "OPS.TON", order), "color": C["blue"]}],
            "unit": "تن", "decimals": 0,
        })
        svc = [("ترانشیپ", ["OPS.TRN.IMP", "OPS.TRN.EXP"]), ("بارگیری", ["OPS.LOD.IMP", "OPS.LOD.EXP"]),
               ("تخلیه", ["OPS.UNL.IMP", "OPS.UNL.EXP"]), ("حمل یکسره", ["OPS.DIR.IMP", "OPS.DIR.EXP"])]
        tables.append({
            "title": "ترکیب عملیات به تفکیک خدمت",
            "columns": ["نوع خدمت", "واردات (تن)", "صادرات (تن)", "جمع (تن)"],
            "rows": [[name,
                      ctx.s(branch, codes[0]),
                      ctx.s(branch, codes[1]),
                      (ctx.s(branch, codes[0]) or 0) + (ctx.s(branch, codes[1]) or 0)]
                     for name, codes in svc],
            "numeric": [1, 2, 3], "decimals": [0, 0, 0],
        })

    elif page == "prj":
        cards = cards_for(kpis, branch, DOMAIN_CARDS["prj"])
        prj = [p for p in ctx.projects if branch in ("مجتمع", p["branch"])]
        order = {}
        for p in prj:
            order.setdefault(p["branch"], [0, 0])
            order[p["branch"]][0] += p["total"] or 0
            order[p["branch"]][1] += 1
        labs = sorted(order, key=lambda b: -order[b][0])
        charts.append({
            "type": "bar", "title": "مبلغ پروژه‌ها به تفکیک شعبه",
            "labels": labs, "horizontal": True,
            "series": [{"name": "م.ریال", "values": [order[b][0] for b in labs], "color": C["purple"]}],
            "unit": "م.ریال", "decimals": 0,
        })
        # فقط شعبی که بودجهٔ مصوب دارند؛ درصد جذب بیش از ۱۰۰ در نمایش محدود می‌شود
        labs_p = [b for b in labs if sum(p["bud6"] or 0 for p in prj if p["branch"] == b) > 0]
        charts.append({
            "type": "bar", "title": "جذب بودجه و پیشرفت فیزیکی به تفکیک شعبه (٪)",
            "labels": labs_p,
            "series": [{"name": "جذب بودجه", "values": [
                min(sum(p["act"] or 0 for p in prj if p["branch"] == b) /
                    (sum(p["bud6"] or 0 for p in prj if p["branch"] == b) or 1) * 100, 150)
                for b in labs_p], "color": C["purple"]},
                {"name": "پیشرفت فیزیکی", "values": [
                    min(sum(p["prog"] or 0 for p in prj if p["branch"] == b) /
                        max(len([1 for p in prj if p["branch"] == b]), 1), 100)
                    for b in labs_p], "color": C["teal"]}],
            "unit": "%", "decimals": 1,
        })
        tables.append({
            "title": "فهرست پروژه‌ها",
            "columns": ["شعبه", "عنوان", "دامنه", "مبلغ کل", "بودجه شش‌ماهه", "جذب", "پیشرفت (٪)"],
            "rows": [[p["branch"], p["title"], p["domain"], p["total"], p["bud6"], p["act"], p["prog"]]
                     for p in sorted(prj, key=lambda x: -(x["total"] or 0))[:14]],
            "numeric": [3, 4, 5, 6], "decimals": [0, 0, 0, 0],
        })

    elif page == "data":
        return _data_quality(conn, kpis, year, period)

    # هشدارهای مرتبط با صفحه
    dom = {"fin": "FIN", "hr": "HR", "pay": "PAY", "wh": "WH", "flt": "FLT",
           "ops": "OPS", "prj": "PRJ"}.get(page)
    page_alerts = [a for a in alerts if not dom or any(x.startswith(dom) for x in a["kpi"])
                   or a["id"] in ("R01", "R02", "R10")]
    if page == "overview":
        page_alerts = alerts

    title, en = PAGE_TITLES[page]
    # بستهٔ واقعیت: کارت‌های صفحه + (برای نمای مدیریتی) همهٔ شاخص‌های سطح مجتمع
    bundle_rows = [{"code": c["code"], "title": c["title"], "unit": c["unit"],
                    "act": c["act"], "bud": c["bud"], "ly": c["ly"]} for c in cards]
    if page == "overview":
        extra_rows = []
        for code in [r[0] for r in catalog.KPI_CATALOG]:
            v = kpis.get(branch, {}).get(code) or {}
            if v.get("act") is None and v.get("ly") is None:
                continue
            m = _meta(code)
            extra_rows.append({"code": code, "title": m["title"], "unit": m["unit"],
                               "act": v.get("act"), "bud": v.get("bud"), "ly": v.get("ly")})
        merged = {r["code"]: r for r in extra_rows}
        for r in bundle_rows:
            merged[r["code"]] = r
        bundle_rows = list(merged.values())
    from .ai import build_bundle
    bundle = build_bundle(bundle_rows, plabel + (" — " + branch if branch != "مجتمع" else ""))

    return {
        "page": page, "title": title, "en": en, "branch": branch, "year": year, "period": period,
        "period_label": plabel,
        "cards": cards, "charts": charts, "tables": tables,
        "alerts": page_alerts,
        "bundle": bundle,
    }


def _bundle_from_cards(cards, period_label):
    rows = [{"code": c["code"], "title": c["title"], "unit": c["unit"],
             "act": c["act"], "bud": c["bud"], "ly": c["ly"]} for c in cards]
    from .ai import build_bundle
    return build_bundle(rows, period_label)


def _data_quality(conn, kpis, year, period):
    from . import catalog as cat
    total_codes = [r[0] for r in cat.KPI_CATALOG]
    rows = []
    branch = "مجتمع"
    for code in total_codes:
        v = (kpis.get(branch, {}).get(code) or {})
        rows.append([_meta(code)["title"], code, v.get("act") is not None,
                     v.get("bud") is not None, v.get("ly") is not None])
    missing_bud = [r[0] for r in rows if not r[3]]
    versions = [dict(r) for r in conn.execute(
        "SELECT id, created, author, note, n_facts FROM data_version ORDER BY id DESC LIMIT 8")]
    n_facts = conn.execute("SELECT COUNT(*) c FROM fact").fetchone()["c"]
    n_kpi = conn.execute("SELECT COUNT(*) c FROM kpi").fetchone()["c"]
    return {
        "page": "data", "title": "کیفیت داده", "en": "Data Quality",
        "branch": branch, "year": year, "period": period,
        "period_label": PERIOD_LABEL.get(period, period) + f" {year}",
        "cards": [
            {"code": "DQ.KPI", "title": "شاخص محاسبه‌شده", "unit": "شاخص",
             "act": len([r for r in rows if r[2]]), "bud": None, "ly": None, "direction": "flat"},
            {"code": "DQ.FACT", "title": "قلم داده خام", "unit": "قلم",
             "act": n_facts, "bud": None, "ly": None, "direction": "flat"},
            {"code": "DQ.NOBUD", "title": "شاخص بدون ستون بودجه", "unit": "شاخص",
             "act": len(missing_bud), "bud": None, "ly": None, "direction": "down"},
            {"code": "DQ.VER", "title": "نسخهٔ داده جاری", "unit": "نسخه",
             "act": versions[0]["id"] if versions else 0, "bud": None, "ly": None, "direction": "flat"},
        ],
        "charts": [{
            "type": "bar", "title": "پوشش داده‌های هر شاخص",
            "labels": ["عملکرد", "بودجه", "دوره مشابه"],
            "series": [{"name": "تعداد شاخص", "values": [
                sum(1 for r in rows if r[2]), sum(1 for r in rows if r[3]),
                sum(1 for r in rows if r[4])], "color": C["teal"]}],
            "unit": "شاخص", "decimals": 0,
        }],
        "tables": [
            {"title": "نسخه‌های داده", "columns": ["نسخه", "تاریخ", "ثبت‌کننده", "توضیح", "تعداد قلم"],
             "rows": [[v["id"], v["created"], v["author"], v["note"], v["n_facts"]] for v in versions],
             "numeric": [0, 4], "decimals": [0, 0]},
            {"title": "شاخص‌های بدون بودجه", "columns": ["شاخص", "کد"],
             "rows": [[c, code] for c, code in zip(
                 [_meta(x)["title"] for x in missing_bud], missing_bud)],
             "numeric": [], "decimals": []},
        ],
        "alerts": [], "bundle": {"period_label": "", "kpis": [], "extra_numbers": []},
    }
