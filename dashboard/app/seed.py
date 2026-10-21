"""درون‌ریزی دادهٔ موجود (سه سال) به پایگاه داده — یک‌بار در شروع."""
import json
from datetime import datetime

from . import catalog
from .config import SOURCE_FILES
from .db import get_db, init_db, new_version

BRANCH_META = {
    "شهید کاوه": ("خراسان رضوی", 1),
    "مطهری": ("خراسان رضوی", 0),
    "سرخس": ("خراسان رضوی", 1),
    "لطف آباد": ("خراسان رضوی", 1),
    "نیشابور": ("خراسان رضوی", 0),
    "ماهیرود": ("خراسان جنوبی", 1),
    "دوغارون": ("خراسان رضوی", 1),
    "بجنورد": ("خراسان شمالی", 0),
    "بیرجند": ("خراسان جنوبی", 0),
    "باجگیران": ("خراسان رضوی", 1),
    "مجتمع": ("ستاد", 0),
}

PROJ_MAP = {"کاوه (مجتمع خراسان)": "شهید کاوه", "شهید مطهری": "مطهری"}


def _load(key):
    p = SOURCE_FILES[key]
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _norm_branch(b: str) -> str:
    b = (b or "").strip()
    return PROJ_MAP.get(b, b)


def seed(force: bool = False) -> dict:
    init_db()
    with get_db() as conn:
        n_facts = conn.execute("SELECT COUNT(*) c FROM fact").fetchone()["c"]
        if n_facts and not force:
            return {"status": "already", "facts": n_facts}

        # ── ابعاد
        conn.executemany(
            "INSERT OR REPLACE INTO dim_branch(name, province, is_border) VALUES(?,?,?)",
            [(b, p, bd) for b, (p, bd) in BRANCH_META.items()],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO dim_metric(code,title,domain,unit,direction,formula,decimals)"
            " VALUES(?,?,?,?,?,?,?)",
            catalog.KPI_CATALOG,
        )

        rows = []  # (branch, year, period, code, month, scenario, value)

        def add(branch, year, code, value, scenario="ACT", month=0, period="H1"):
            if value is None:
                return
            rows.append((branch, int(year), period, code, int(month), scenario, float(value)))

        real = _load("real_all")
        ops = _load("ops3")
        mod = _load("mod")
        fuel = _load("fuel")

        # ── مالی (سه سال) از گزارش مدیریتی شعب
        if mod:
            for br, m in mod.items():
                if br not in BRANCH_META:
                    continue
                for i, year in enumerate((1403, 1404, 1405)):
                    pl = m.get("pl", {})
                    rev = pl.get("rev", [0, 0, 0])[i]
                    cogs = abs(pl.get("cogs", [0, 0, 0])[i])
                    admin = abs(pl.get("admin", [0, 0, 0])[i])
                    other = pl.get("other_inc", [0, 0, 0])[i]
                    net = pl.get("net", [0, 0, 0])[i]
                    for sc, yy in (("ACT", year), ("LY", year + 1)):
                        if yy > 1405:
                            continue
                        add(br, yy, "FIN.REV", rev, sc)
                        add(br, yy, "FIN.COGS", cogs, sc)
                        add(br, yy, "FIN.ADMIN", admin, sc)
                        add(br, yy, "FIN.OTHER", other, sc)
                        add(br, yy, "FIN.NET.REP", net, sc)

        # ── عملیات: تناژ ماهانه به تفکیک خدمت و جهت
        # مبنا: فایل آمار عملیات (جمع شش‌ماهه)؛ تفکیک واردات/صادرات از همان منبع
        # و صادرات = جمع − واردات، تا جمع هر خدمت همیشه با مبنای کل برابر بماند.
        if ops:
            for year, block in ops.items():
                agg = block.get("تجمیعی", {})
                imp = block.get("واردات", {})
                exp = block.get("صادرات", {})
                for br, data in agg.items():
                    if br not in BRANCH_META:
                        continue
                    for svc, code in (("unload", "OPS.UNL"), ("load", "OPS.LOD"), ("trans", "OPS.TRN")):
                        a = data.get(svc)
                        if not isinstance(a, list):
                            continue
                        p_ = (imp.get(br, {}) or {}).get(svc)
                        e_ = (exp.get(br, {}) or {}).get(svc)
                        for idx in range(min(6, len(a))):
                            total = a[idx] or 0
                            if isinstance(p_, list) and idx < len(p_) and p_[idx] is not None:
                                iv = p_[idx] or 0
                                ev = total - iv
                            elif isinstance(e_, list) and idx < len(e_) and e_[idx] is not None:
                                ev = e_[idx] or 0
                                iv = total - ev
                            else:
                                iv, ev = total, 0.0
                            for sc, yy in (("ACT", int(year)), ("LY", int(year) + 1)):
                                if yy > 1405:
                                    continue
                                add(br, yy, code + ".IMP", iv, sc, month=idx + 1)
                                add(br, yy, code + ".EXP", ev, sc, month=idx + 1)
                    for svc, code in (("direct", "OPS.DIR"), ("rosoob", "OPS.ROS")):
                        a = data.get(svc)
                        if not isinstance(a, list):
                            continue
                        for idx in range(min(6, len(a))):
                            for sc, yy in (("ACT", int(year)), ("LY", int(year) + 1)):
                                if yy > 1405:
                                    continue
                                add(br, yy, code + ".IMP", a[idx] or 0, sc, month=idx + 1)

        # ── نیروی انسانی
        if real:
            for br, h in real.get("hr", {}).items():
                if br not in BRANCH_META:
                    continue
                for scenario, key in (("ACT", "act"), ("BUD", "bud"), ("LY", "last")):
                    v = (h.get(key) or [0, 0, 0, 0])
                    if len(v) >= 3:
                        add(br, 1405, "HR.TEMP", v[1], scenario)
                        add(br, 1405, "HR.CONTR", v[2], scenario)

            # ── انبار
            for br0, types in real.get("wh", {}).items():
                br = "مجتمع" if br0 == "جمع کل" else br0
                if br not in BRANCH_META:
                    continue
                for t, d in types.items():
                    code_t = {"مسقف": "ROOFED", "هانگار": "HANGAR", "بارانداز": "YARD"}.get(t)
                    if not code_t:
                        continue
                    for k, fcode in (("count", "WH.COUNT"), ("area", "WH.AREA"), ("cap", "WH.CAP"),
                                     ("empty", "WH.EMPTY"), ("unload", "WH.UNLOAD"),
                                     ("load", "WH.LOAD"), ("rosoob", "WH.ROSOOB")):
                        add(br, 1405, f"{fcode}.{code_t}", d.get(k, 0))

            # ── ناوگان
            for br0, m in real.get("mach", {}).items():
                br = "مجتمع" if br0 == "جمع کل" else br0
                if br not in BRANCH_META:
                    continue
                groups = m.get("groups", {}) or {}
                # چهار گروه عملیاتی جدا؛ بقیه بر اساس تصمیم کارفرما در «سایر» و «آتش‌نشانی» جمع می‌شوند
                mapping = {
                    "جرثقیل": "FLT.CRANE", "لیفتراک (دیزلی)": "FLT.FORK", "تراکتور": "FLT.TRAC",
                    "جک پالت دستی": "FLT.PALLET",
                }
                fire_keys = ("پیشرو آتش نشانی", "کامیون آتش نشانی", "موتور سیکلت آتش نشانی")
                fire = sum(groups.get(k, 0) for k in fire_keys)
                for g, code in mapping.items():
                    add(br, 1405, code, groups.get(g, 0))
                rest = sum(v for k, v in groups.items()
                           if k not in mapping and k not in fire_keys)
                add(br, 1405, "FLT.FIRE", fire)
                add(br, 1405, "FLT.OTHER", rest)

        if fuel:
            for br, d in fuel.items():
                if br not in BRANCH_META:
                    continue
                add(br, 1405, "FLT.FUEL", d.get("fuel", 0))
                add(br, 1405, "FLT.REP", d.get("repair", 0))

        # ── ترکیب مشاغل (سطح مجتمع) از فایل اطلاعات کارکنان
        st = _load("staff")
        if st and st.get("staff"):
            post = st["staff"].get("post", {}) or {}
            n_all = st["staff"].get("n", 0) or 0
            ops_jobs = (post.get("عملیات و صدور اسناد", 0) + post.get("رانندگان و اپراتورها", 0)
                        + post.get("انبارداری", 0))
            add("مجتمع", 1405, "HR.JOB.OPS", ops_jobs)
            add("مجتمع", 1405, "HR.JOB.TOT", n_all)
            for i, (k, v) in enumerate(sorted(post.items(), key=lambda kv: -kv[1]), start=1):
                add("مجتمع", 1405, f"HR.JOB.G{i}", v)

        # ── بودجهٔ سطح مجتمع (از فایل بودجهٔ شش‌ماهه)
        if real:
            bud = real.get("bud", {})
            tot_pay = bud.get("tot_payroll") or [0, 0, 0]     # [سال قبل, بودجه, عملکرد]
            tot_oh = bud.get("tot_overhead") or [0, 0, 0]
            tot_ad = bud.get("tot_admin") or [0, 0, 0]
            if len(tot_pay) == 3:
                add("مجتمع", 1405, "PAY.TOT", tot_pay[2], "ACT")
                add("مجتمع", 1405, "PAY.TOT", tot_pay[1], "BUD")
                add("مجتمع", 1405, "PAY.TOT", tot_pay[0], "LY")
            if len(tot_oh) == 3:
                add("مجتمع", 1405, "FIN.OH", tot_oh[2], "ACT")
                add("مجتمع", 1405, "FIN.OH", tot_oh[1], "BUD")
            if len(tot_ad) == 3:
                add("مجتمع", 1405, "FIN.ADMIN", tot_ad[2], "ACT")
                add("مجتمع", 1405, "FIN.ADMIN", tot_ad[1], "BUD")
            cb = {r.get("lab", ""): r for r in bud.get("costbuild", [])}
            for lab, r in cb.items():
                if "بهاي خدمات" in lab or "بهای خدمات" in lab:
                    add("مجتمع", 1405, "FIN.COGS", r.get("act"), "ACT")
                    add("مجتمع", 1405, "FIN.COGS", r.get("bud"), "BUD")
            fz = bud.get("fuel", {}).get("tot")
            if fz and len(fz) == 3:
                add("مجتمع", 1405, "FLT.COST.TOT", fz[2], "ACT")
                add("مجتمع", 1405, "FLT.COST.TOT", fz[1], "BUD")
                add("مجتمع", 1405, "FLT.COST.TOT", fz[0], "LY")

        conn.executemany(
            "INSERT OR REPLACE INTO fact(branch,year,period,code,month,scenario,value,version)"
            " VALUES(?,?,?,?,?,?,?,1)", rows,
        )

        # ── پروژه‌ها
        if real:
            projs = []
            for i, p in enumerate(real.get("proj", []), start=1):
                br = _norm_branch(p.get("br", ""))
                projs.append((
                    f"1405-{i:03d}", br, p.get("title", ""), p.get("dom", ""),
                    p.get("total", 0) or 0, p.get("bud6", 0) or 0, p.get("act", 0) or 0,
                    p.get("prog", 0) or 0, p.get("months", 0) or 0, 0, 1405, "H1",
                ))
            conn.executemany(
                "INSERT OR REPLACE INTO project(pid,branch,title,domain,total,bud6,act,prog,months,start,year,period)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", projs,
            )

        vid = new_version(conn, "درون‌ریزی اولیه", "بارگذاری دادهٔ سه سال از فایل‌های موجود")
        conn.execute("UPDATE fact SET version=?", (vid,))
        return {"status": "seeded", "facts": len(rows), "version": vid}


if __name__ == "__main__":
    print(seed(force=True))
