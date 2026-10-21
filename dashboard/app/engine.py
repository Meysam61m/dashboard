"""موتور شاخص — همهٔ اعداد اینجا و فقط اینجا محاسبه می‌شوند.

هیچ عددی در فرانت‌اند یا در لایهٔ هوش مصنوعی محاسبه نمی‌شود.
"""
from __future__ import annotations

from . import catalog

OPS_CODES = ["OPS.UNL.IMP", "OPS.UNL.EXP", "OPS.LOD.IMP", "OPS.LOD.EXP",
             "OPS.TRN.IMP", "OPS.TRN.EXP", "OPS.DIR.IMP", "OPS.DIR.EXP"]
OPS_DEV_CODES = ["FLT.CRANE", "FLT.FORK", "FLT.TRAC", "FLT.PALLET"]
FLT_ALL = ["FLT.CRANE", "FLT.FORK", "FLT.TRAC", "FLT.PALLET", "FLT.OTHER", "FLT.FIRE"]
WH_CODES = ["ROOFED", "HANGAR", "YARD"]


def _div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def _pct(a, b):
    d = _div(a, b)
    return None if d is None else d * 100.0


class Ctx:
    """دسترسی سریع به دادهٔ خام یک سال."""

    def __init__(self, conn, year: int):
        self.year = year
        self.f: dict[tuple, float] = {}
        self.m: dict[tuple, float] = {}
        for r in conn.execute(
            "SELECT branch, code, scenario, month, value FROM fact WHERE year=?", (year,)
        ):
            key = (r["branch"], r["code"], r["scenario"])
            self.f[key] = self.f.get(key, 0.0) + (r["value"] or 0.0)
            if r["month"]:
                self.m[(r["branch"], r["code"], r["scenario"], r["month"])] = r["value"] or 0.0
        self.projects = [dict(r) for r in conn.execute(
            "SELECT * FROM project WHERE year=?", (year,))]
        self.branches = [r["name"] for r in conn.execute(
            "SELECT name FROM dim_branch WHERE active=1 ORDER BY rowid")]

    # ── دسترسی
    def s(self, branch: str, code: str, scenario: str = "ACT"):
        return self.f.get((branch, code, scenario))

    def sv(self, branch: str, codes, scenario: str = "ACT"):
        vals = [self.s(branch, c, scenario) for c in codes]
        if any(v is None for v in vals):
            return None
        return sum(vals)

    def ops_char(self, branch: str, scenario: str = "ACT"):
        """تناژ مبنای عملیات: تخلیه+بارگیری+ترانشیپ+حمل یکسره (بدون روزوب)."""
        vals = [self.s(branch, c, scenario) for c in OPS_CODES]
        if all(v is None for v in vals):
            return None
        return sum(v for v in vals if v is not None)

    def ops_wh(self, branch: str):
        """تناژ مبنای بهره‌وری ناوگان: باربری + ترانشیپ."""
        v = [self.s(branch, c) for c in ("OPS.LOD.IMP", "OPS.LOD.EXP", "OPS.TRN.IMP", "OPS.TRN.EXP")]
        if all(x is None for x in v):
            return None
        return sum(x for x in v if x is not None)

    def monthly_ops(self, branch: str, months=6):
        out = []
        for i in range(1, months + 1):
            out.append(sum(self.m.get((branch, c, "ACT", i), 0.0) for c in OPS_CODES))
        return out


def _fin(ctx: Ctx, b: str, sc: str):
    rev_s = ctx.s(b, "FIN.REV", sc)
    other = ctx.s(b, "FIN.OTHER", sc) or 0.0
    cogs = ctx.s(b, "FIN.COGS", sc)
    admin = ctx.s(b, "FIN.ADMIN", sc)
    if rev_s is None or cogs is None:
        return None, None, None
    rev = rev_s + other
    cost = cogs + (admin or 0.0)
    return rev, cost, rev - cost


def compute_branch(ctx: Ctx, b: str) -> dict:
    """شاخص‌های یک شعبه (یا مجتمع) در سال جاری."""
    out: dict[str, dict] = {}

    def put(code, act=None, bud=None, ly=None):
        out[code] = {"act": act, "bud": bud, "ly": ly}

    # ── مالی
    rev_a, cost_a, net_a = _fin(ctx, b, "ACT")
    rev_b, cost_b, net_b = _fin(ctx, b, "BUD")
    rev_l, cost_l, net_l = _fin(ctx, b, "LY")
    put("FIN.REV", rev_a, rev_b, rev_l)
    put("FIN.COST", cost_a, cost_b, cost_l)
    put("FIN.NET", net_a, net_b, net_l)
    put("FIN.MARGIN", _pct(net_a, rev_a), _pct(net_b, rev_b), _pct(net_l, rev_l))
    put("FIN.BUD.ACHV", _pct(net_a, net_b) if net_b else None)
    put("FIN.GROW", _pct(net_a - net_l, abs(net_l)) if net_l not in (None, 0) else None)
    put("FIN.COST.RATIO", _pct(cost_a, rev_a), _pct(cost_b, rev_b), _pct(cost_l, rev_l))
    cogs_a = ctx.s(b, "FIN.COGS")
    oh_a = ctx.s(b, "FIN.OH")
    put("FIN.COGS", cogs_a, ctx.s(b, "FIN.COGS", "BUD"), ctx.s(b, "FIN.COGS", "LY"))
    put("FIN.OH.SHARE", _pct(oh_a, cogs_a) if oh_a is not None else None)

    # ── نیروی انسانی
    temp_a, con_a = ctx.s(b, "HR.TEMP"), ctx.s(b, "HR.CONTR")
    head_a = (temp_a or 0) + (con_a or 0) if (temp_a is not None or con_a is not None) else None
    temp_b, con_b = ctx.s(b, "HR.TEMP", "BUD"), ctx.s(b, "HR.CONTR", "BUD")
    head_b = (temp_b or 0) + (con_b or 0) if (temp_b is not None or con_b is not None) else None
    temp_l, con_l = ctx.s(b, "HR.TEMP", "LY"), ctx.s(b, "HR.CONTR", "LY")
    head_l = (temp_l or 0) + (con_l or 0) if (temp_l is not None or con_l is not None) else None
    put("HR.HEAD", head_a, head_b, head_l)
    put("HR.TEMP.SHARE", _pct(temp_a, head_a), _pct(temp_b, head_b), _pct(temp_l, head_l))
    put("HR.CONTR.SHARE", _pct(con_a, head_a), _pct(con_b, head_b), _pct(con_l, head_l))
    put("HR.BUD.ACHV", _pct(head_a, head_b))
    jobs_ops, jobs_tot = ctx.s(b, "HR.JOB.OPS"), ctx.s(b, "HR.JOB.TOT")
    put("HR.OPS.SHARE", _pct(jobs_ops, jobs_tot or head_a))

    # ── هزینهٔ پرسنلی
    pay_a = ctx.s(b, "PAY.TOT")
    if pay_a is None:
        vals = [ctx.s(b, f"PAY.{i:02d}") for i in range(1, 21)]
        pay_a = sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None
    put("PAY.TOT", pay_a, ctx.s(b, "PAY.TOT", "BUD"), ctx.s(b, "PAY.TOT", "LY"))
    put("PAY.BUD.ACHV", _pct(pay_a, ctx.s(b, "PAY.TOT", "BUD")))
    pay_l = ctx.s(b, "PAY.TOT", "LY")
    put("PAY.GROW", _pct(pay_a - pay_l, abs(pay_l)) if pay_l else None)
    put("PAY.PER.HEAD", _div(pay_a, head_a))

    # ── انبار
    cnt = ctx.sv(b, [f"WH.COUNT.{t}" for t in WH_CODES])
    area = ctx.sv(b, [f"WH.AREA.{t}" for t in WH_CODES])
    cap = ctx.sv(b, [f"WH.CAP.{t}" for t in WH_CODES])
    empty = ctx.sv(b, [f"WH.EMPTY.{t}" for t in WH_CODES])
    put("WH.COUNT", cnt)
    put("WH.AREA", area)
    occ = _pct((cap or 0) - (empty or 0), cap) if cap else None
    put("WH.OCC", occ)
    put("WH.PROFIT.M2", _div(net_a, area))
    wh_flow = ctx.sv(b, ["WH.UNLOAD.ROOFED", "WH.UNLOAD.HANGAR", "WH.UNLOAD.YARD",
                         "WH.LOAD.ROOFED", "WH.LOAD.HANGAR", "WH.LOAD.YARD"])
    put("WH.TON.M2", _div(wh_flow, area))

    # ── ناوگان
    put("FLT.COUNT", ctx.sv(b, FLT_ALL))
    base = ctx.sv(b, OPS_DEV_CODES)
    put("FLT.OPS.BASE", base)
    put("FLT.TON.DEV", _div(ctx.ops_wh(b), base))
    fuel, rep = ctx.s(b, "FLT.FUEL"), ctx.s(b, "FLT.REP")
    fr = (fuel + rep) if (fuel is not None or rep is not None) else None
    put("FLT.COST.TON", _div((fr or 0) * 1_000_000, ctx.ops_char(b)) if fr is not None else None)
    fuel_bud = ctx.s(b, "FLT.COST.TOT", "BUD")
    if fuel_bud is None:
        fuel_bud = ctx.s(b, "FLT.FUEL", "BUD")
    put("FLT.FUEL.BUD", _pct(fr, fuel_bud) if fr is not None and fuel_bud else None)

    # ── عملیات
    ops = ctx.ops_char(b)
    ops_l = ctx.ops_char(b, "LY")
    put("OPS.TON", ops, None, ops_l)
    put("OPS.MOM", _div(ops, 6), None, _div(ops_l, 6))
    trn = ctx.sv(b, ["OPS.TRN.IMP", "OPS.TRN.EXP"])
    trn_l = ctx.sv(b, ["OPS.TRN.IMP", "OPS.TRN.EXP"], "LY")
    put("OPS.TRANS.SHARE", _pct(trn, ops), None, _pct(trn_l, ops_l))

    # ── پروژه
    prj = [p for p in ctx.projects if (b == "مجتمع" or p["branch"] == b)]
    if prj:
        put("PRJ.COUNT", len(prj))
        # میانگین سادهٔ پیشرفت (هم‌راستا با گزارش فعلی)
        put("PRJ.PROG", sum((p["prog"] or 0) for p in prj) / len(prj))
        put("PRJ.ABSORB", _pct(sum(p["act"] or 0 for p in prj), sum(p["bud6"] or 0 for p in prj)))
        # پروژه‌هایی که بودجهٔ مصوب دارند ولی هیچ جذبی نداشته‌اند (اجرا شروع نشده)
        put("PRJ.OVERDUE", sum(1 for p in prj if (p["bud6"] or 0) > 0 and (p["act"] or 0) == 0))
    else:
        put("PRJ.COUNT", 0)

    return out


def compute_all(ctx: Ctx) -> dict[str, dict]:
    """شاخص همهٔ شعب + مجتمع، به‌همراه شاخص‌های وابسته به کل (تمرکز، فضای زیان‌ده، FEI)."""
    res = {}
    for b in ctx.branches:
        res[b] = compute_branch(ctx, b)

    brs = [b for b in ctx.branches if b != "مجتمع"]

    # تمرکز عملیات (سهم دو شعبهٔ نخست)
    vals = sorted(((res[b].get("OPS.TON", {}).get("act") or 0), b) for b in brs)
    top2 = sum(v for v, _ in vals[-2:])
    tot = sum(v for v, _ in vals)
    res["مجتمع"]["OPS.CONC"] = {"act": _pct(top2, tot), "bud": None, "ly": None}

    # سهم فضای شعب زیان‌ده
    area_all = sum(res[b].get("WH.AREA", {}).get("act") or 0 for b in brs)
    area_loss = sum(res[b].get("WH.AREA", {}).get("act") or 0 for b in brs
                    if (res[b].get("FIN.NET", {}).get("act") or 0) <= 0)
    res["مجتمع"]["WH.LOSS.AREA"] = {"act": _pct(area_loss, area_all), "bud": None, "ly": None}

    # شاخص کارایی ناوگان — نرمال‌سازی نسبت به میانگین مجتمع
    tpd = {b: res[b].get("FLT.TON.DEV", {}).get("act") for b in brs
           if res[b].get("FLT.TON.DEV", {}).get("act")}
    tpf = {b: (_div(ctx.ops_char(b) or 0, (ctx.s(b, "FLT.FUEL") or 0) + (ctx.s(b, "FLT.REP") or 0))
               if ((ctx.s(b, "FLT.FUEL") or 0) + (ctx.s(b, "FLT.REP") or 0)) else None) for b in brs}
    tpf = {k: v for k, v in tpf.items() if v}
    if tpd and tpf:
        a1 = sum(tpd.values()) / len(tpd)
        a2 = sum(tpf.values()) / len(tpf)
        for b in brs:
            if b in tpd and b in tpf:
                res[b]["FLT.FEI"] = {
                    "act": round(100 * (0.5 * tpd[b] / a1 + 0.5 * tpf[b] / a2)),
                    "bud": None, "ly": None,
                }
        res["مجتمع"]["FLT.FEI"] = {"act": 100, "bud": None, "ly": None}

    return res


def save_kpis(conn, res: dict, year: int, period: str = "H1"):
    rows = []
    for b, kpis in res.items():
        for code, v in kpis.items():
            rows.append((b, year, period, code, v.get("act"), v.get("bud"), v.get("ly")))
    conn.executemany(
        "INSERT OR REPLACE INTO kpi(branch,year,period,code,act,bud,ly) VALUES(?,?,?,?,?,?,?)", rows)
    return len(rows)


def run(conn, year: int = 1405, period: str = "H1") -> dict:
    ctx = Ctx(conn, year)
    res = compute_all(ctx)
    n = save_kpis(conn, res, year, period)
    return {"rows": n, "branches": len(res)}
