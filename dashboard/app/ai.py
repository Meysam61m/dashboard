"""اتصال به Ollama — تحلیل متنی از روی اعداد تأییدشده.

قاعدهٔ طلایی: مدل هیچ عددی محاسبه نمی‌کند. فقط «بستهٔ واقعیت» را می‌خواند و متن می‌نویسد.
هر عددی که در پاسخ بیاید و در بستهٔ واقعیت نباشد، علامت‌گذاری می‌شود.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime

import httpx

from . import catalog
from .config import (AI_MAX_TOKENS, AI_TEMPERATURE, MODEL_ANALYSIS, MODEL_CHAT,
                     MODEL_DEEP, OLLAMA_HOST, OLLAMA_TIMEOUT)

PROMPT_VERSION = "v1.3"

SYSTEM_PROMPT = """تو یک تحلیل‌گر مالی و عملیاتی برای مجتمع انبارهای عمومی خراسان هستی.
تحلیل را فقط بر پایهٔ «بستهٔ واقعیت» که به تو داده می‌شود بنویس.

قواعد سخت‌گیرانه:
۱. هیچ عددی که در بستهٔ واقعیت نیست ننویس. هیچ محاسبهٔ جدیدی انجام نده.
۲. اگر شاخصی در بسته نیست، در data_gaps بنویس؛ حدس نزن.
۳. «علت» را فقط وقتی بنویس که داده‌ای برایش وجود دارد؛ در غیر این صورت از عبارت «هم‌روند با» استفاده کن، نه «به دلیل».
۴. فارسی روان و اداری بنویس؛ از حروف لاتین و علامت‌های تزئینی استفاده نکن.
۵. خروجی فقط JSON معتبر باشد، بدون توضیح اضافه و بدون بلوک کد.

قالب خروجی:
{
  "headline": "یک جملهٔ اصلی، حداکثر ۲۵ کلمه",
  "findings": [{"kpi": "کد شاخص", "text": "یافته", "direction": "up|down|flat"}],
  "drivers": ["عامل هم‌روند قابل استناد"],
  "risks": ["ریسک"],
  "actions": ["اقدام پیشنهادی مشخص"],
  "data_gaps": ["شاخص یا دادهٔ ناقص"]
}
حداکثر ۳ یافته، ۳ عامل، ۳ ریسک و ۳ اقدام بنویس. کوتاه بنویس."""


# ── کمکی‌ها
FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def fa_num(s: str) -> str:
    for i, d in enumerate(FA_DIGITS):
        s = s.replace(str(i), d)
    return s


def _fmt_set(values) -> set[str]:
    """همهٔ شکل‌های قابل قبول اعداد بسته — برای اعتبارسنجی."""
    out = set()
    for v in values:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        for d in (0, 1, 2):
            s = f"{f:,.{d}f}"
            out.add(s)
            out.add(fa_num(s))
            out.add(s.replace(",", "٬"))
            out.add(fa_num(s.replace(",", "٬")))
        out.add(str(int(round(f))))
        out.add(fa_num(str(int(round(f)))))
        out.add(f"{abs(f):,.0f}")
        out.add(fa_num(f"{abs(f):,.0f}"))
    return out


NUM_RE = re.compile(r"[۰-۹0-9][۰-۹0-9,٬٫\.]*")
FA2EN = {ord(a): ord(b) for a, b in zip("۰۱۲۳۴۵۶۷۸۹", "0123456789")}


def _norm_num(tok: str) -> str:
    """ارقام فارسی، جداکنندهٔ هزارگان و اعشار بومی را به شکل لاتین استاندارد برمی‌گرداند."""
    t = tok.translate(FA2EN)
    t = t.replace("٬", ",").replace("٫", ".")
    t = t.rstrip(".,")
    return t


def _canon(tok: str) -> float | None:
    t = _norm_num(tok).replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def validate_numbers(texts: list[str], allowed: set[str], allowed_values=None) -> dict:
    """هر عدد متن با اعداد بستهٔ واقعیت مقایسه می‌شود.

    تطبیق هم رشته‌ای و هم عددی انجام می‌شود تا ارقام فارسی/لاتین و
    جداکنندهٔ اعشار بومی مشکلی ایجاد نکند.
    """
    canon_allowed = {round(_canon(a), 2) for a in allowed if _canon(a) is not None}
    if allowed_values:
        canon_allowed |= {round(float(v), 2) for v in allowed_values if v is not None}

    found, bad = set(), set()
    for t in texts:
        for raw in NUM_RE.findall(t or ""):
            tok = raw.rstrip(".,٬٫")
            if not tok:
                continue
            val = _canon(tok)
            if val is None:
                continue
            ok = round(val, 2) in canon_allowed or tok in allowed or _norm_num(tok) in allowed
            if ok:
                found.add(tok)
            elif len(re.sub(r"[^0-9]", "", _norm_num(tok))) >= 2:
                bad.add(tok)
    return {"checked": len(found) + len(bad), "accepted": len(found), "unknown": sorted(bad)}


# ── اتصال
# نکتهٔ مهم: trust_env=False
# بدون این گزینه، httpx متغیرهای HTTP_PROXY / ALL_PROXY سیستم را رعایت می‌کند و
# درخواست به 127.0.0.1 را هم از پروکسی عبور می‌دهد — همان چیزی که باعث می‌شود
# مرورگر Ollama را ببیند ولی برنامه نبیند.
def host() -> str:
    return (_ACTIVE_HOST or OLLAMA_HOST).rstrip("/")


_ACTIVE_HOST: str | None = None
_last_probe: dict = {}


def _candidates() -> list[str]:
    """آدرس‌های ممکن به‌ترتیب اولویت — برای عبور از تفاوت localhost/127.0.0.1/IPv6."""
    base = OLLAMA_HOST.rstrip("/")
    out = [base]
    for alt in ("http://127.0.0.1:11434", "http://localhost:11434",
                "http://[::1]:11434", "http://host.docker.internal:11434"):
        if alt.rstrip("/") != base and alt not in out:
            out.append(alt)
    return out


def _has_model(names: list[str], want: str) -> bool:
    """تطبیق دقیق. اگر نسخهٔ درخواستی برچسب داشته باشد، همان برچسب لازم است
    (qwen3.5:4b نباید جای qwen3.5:9b پذیرفته شود)."""
    if want in names:
        return True
    if ":" not in want:
        return any(n.split(":")[0] == want for n in names)
    return False


def _probe(url: str) -> tuple[bool, int, list[str], str]:
    try:
        t0 = time.time()
        r = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=4.0, trust_env=False)
        r.raise_for_status()
        ms = int((time.time() - t0) * 1000)
        models = [m.get("name") or m.get("model") for m in r.json().get("models", [])]
        return True, ms, [m for m in models if m], ""
    except Exception as e:  # noqa: BLE001
        return False, 0, [], f"{type(e).__name__}: {e}"


def _classify(err: str) -> str:
    e = err.lower()
    if "proxy" in e or "407" in e:
        return "پروکسی سیستم جلوی درخواست را گرفته است (trust_env باید خاموش باشد)."
    if "refused" in e or "connect" in e:
        return ("سرویس Ollama روی این نشانی گوش نمی‌دهد. "
                "یا Ollama اجرا نشده، یا فقط روی loopback دیگری گوش می‌دهد.")
    if "timeout" in e or "timed out" in e:
        return "پاسخی نیامد (timeout). احتمالاً Ollama مشغول بارگذاری مدل است."
    if "name or service" in e or "getaddrinfo" in e:
        return "نشانی قابل تبدیل به IP نبود — مقدار OLLAMA_HOST را بررسی کنید."
    return "خطای نامشخص در تماس با Ollama."


def health() -> dict:
    global _ACTIVE_HOST, _last_probe
    conf = {"chat": MODEL_CHAT, "analysis": MODEL_ANALYSIS, "deep": MODEL_DEEP}
    tried = []
    first_err = ""
    for i, url in enumerate(_candidates()):
        if i > 0 and _ACTIVE_HOST:      # اگر قبلاً آدرسی جواب داده، دوباره همه را نمی‌گردیم
            break
        ok, ms, names, err = _probe(url)
        tried.append({"host": url, "ok": ok, "error": err})
        if ok:
            _ACTIVE_HOST = url
            return {
                "online": True, "latency_ms": ms, "host": url,
                "host_configured": OLLAMA_HOST.rstrip("/"),
                "switched": url.rstrip("/") != OLLAMA_HOST.rstrip("/"),
                "models": names, "configured": conf,
                        "installed": {k: _has_model(names, v) for k, v in conf.items()},
                "engine": "ollama", "tried": tried,
            }
        if not first_err:
            first_err = err
    _ACTIVE_HOST = None
    return {
        "online": False, "host": OLLAMA_HOST.rstrip("/"), "error": first_err,
        "error_text": _classify(first_err), "models": [], "configured": conf,
        "installed": {"chat": False, "analysis": False, "deep": False},
        "engine": "ollama", "tried": tried,
    }


def _chat(model: str, messages: list[dict], max_tokens: int = AI_MAX_TOKENS) -> str:
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": AI_TEMPERATURE,
            "num_predict": max_tokens,
            "num_ctx": 8192,          # پنجرهٔ کوچک: روی CPU سریع‌تر و کم‌مصرف‌تر
            "top_p": 0.9,
        },
    }
    with httpx.Client(timeout=OLLAMA_TIMEOUT, trust_env=False) as c:
        r = c.post(f"{host()}/api/chat", json=body)
        r.raise_for_status()
        data = r.json()
    return (data.get("message") or {}).get("content", "") or ""


def _parse_json(txt: str):
    txt = txt.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\n?", "", txt)
        txt = re.sub(r"\n?```$", "", txt)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", txt, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _normalize(payload: dict) -> dict:
    def lst(x, n=3):
        if isinstance(x, str):
            return [x][:n]
        if isinstance(x, list):
            return [str(i) for i in x if str(i).strip()][:n]
        return []
    out = {
        "headline": str(payload.get("headline", "")).strip(),
        "findings": [],
        "drivers": lst(payload.get("drivers")),
        "risks": lst(payload.get("risks")),
        "actions": lst(payload.get("actions")),
        "data_gaps": lst(payload.get("data_gaps")),
    }
    for f in (payload.get("findings") or [])[:3]:
        if isinstance(f, dict):
            out["findings"].append({
                "kpi": str(f.get("kpi", "")),
                "text": str(f.get("text", "")),
                "direction": str(f.get("direction", "flat")),
            })
        elif isinstance(f, str):
            out["findings"].append({"kpi": "", "text": f, "direction": "flat"})
    return out


def _all_texts(p: dict) -> list[str]:
    t = [p.get("headline", "")]
    t += [f.get("text", "") for f in p.get("findings", [])]
    t += p.get("drivers", []) + p.get("risks", []) + p.get("actions", [])
    return t


# ── تحلیل قاعده‌محور (وقتی مدل در دسترس نیست)
def _fa(text: str) -> str:
    return fa_num(str(text)).replace(",", "٬").replace(".", "٫")


def rules_narrative(bundle: dict, alerts: list[dict]) -> dict:
    kpis = {k["code"]: k for k in bundle.get("kpis", [])}
    head = []
    net = kpis.get("FIN.NET")
    if net and net.get("act") is not None:
        head.append(_fa(f"سود خالص {net['act']:,.0f} میلیون ریال")
                    + (_fa(f" با حاشیهٔ {kpis['FIN.MARGIN']['act']:.1f}٪") if kpis.get("FIN.MARGIN", {}).get("act") is not None else ""))
    ops = kpis.get("OPS.TON")
    if ops and ops.get("act") is not None:
        head.append(_fa(f"تناژ عملیات {ops['act']:,.0f} تن"))
    # اگر شاخص‌های مالی در این صفحه نبودند، از دو شاخص نخستِ موجود جمله بساز
    if not head:
        for k in bundle.get("kpis", [])[:2]:
            if k.get("act") is None:
                continue
            v = k["act"]
            dec = 1 if (abs(v) < 100 and abs(v - round(v)) > 0.001) else 0
            txt_v = _fa(f"{v:,.{dec}f}")
            head.append(f"{k['title']} {txt_v} {k.get('unit','')}".strip())
    if alerts:
        head.append(_fa(alerts[0]["title"]))
    findings = []
    for a in alerts[:3]:
        findings.append({"kpi": ",".join(a.get("kpi", [])), "text": _fa(a["title"] + " — " + a["detail"]),
                         "direction": "down" if a["severity"] in ("high", "med") else "flat"})
    return {
        "headline": "؛ ".join(head) + "." if head else "شاخص‌های این صفحه محاسبه شده‌اند.",
        "findings": findings,
        "drivers": [_fa(a["title"]) for a in alerts[:3]],
        "risks": [a["title"] for a in alerts if a["severity"] == "high"][:3],
        "actions": ["بررسی شاخص‌های دارای هشدار در جلسهٔ ماهانه"] if alerts else [],
        "data_gaps": [c for c, k in kpis.items() if k.get("act") is None][:5],
    }


# ── تحلیل اصلی
def analyze(conn, scope_key: str, scope_label: str, bundle: dict,
            alerts: list[dict], model: str | None = None, force: bool = False) -> dict:
    from .db import current_version

    model = model or MODEL_ANALYSIS
    ver = current_version(conn)
    key = hashlib.sha256(
        json.dumps({"scope": scope_key, "v": ver, "model": model, "p": PROMPT_VERSION},
                   sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:32]

    if not force:
        row = conn.execute("SELECT * FROM ai_analysis WHERE key=?", (key,)).fetchone()
        if row:
            return {
                "status": "cached", "source": row["source"], "model": row["model"],
                "created": row["created"], "payload": json.loads(row["payload"]),
                "validation": json.loads(row["validation"]), "cached": True,
            }

    raw_values = [v for k in bundle.get("kpis", [])
                  for v in (k.get("act"), k.get("bud"), k.get("ly"))] + list(bundle.get("extra_numbers", []))
    # اعداد متن هشدارها هم مجازند: هشدارها را لایهٔ قواعد قطعی از همین داده ساخته است
    for a in alerts:
        for tok in NUM_RE.findall(a.get("title", "") + " " + a.get("detail", "")):
            val = _canon(tok)
            if val is not None:
                raw_values.append(val)
    allowed = _fmt_set(raw_values)

    user_msg = (
        f"دامنه: {scope_label}\n"
        f"دوره: {bundle.get('period_label')}\n\n"
        "بستهٔ واقعیت (تنها منبع مجاز اعداد):\n"
        + json.dumps(bundle, ensure_ascii=False, indent=1)
        + "\n\nهشدارهای قواعد:\n"
        + json.dumps([{"id": a["id"], "severity": a["severity"], "title": a["title"],
                       "detail": a["detail"]} for a in alerts[:6]], ensure_ascii=False, indent=1)
        + "\n\nحالا تحلیل را در قالب JSON بنویس."
    )

    t0 = time.time()
    err = None
    payload = None
    raw = ""
    try:
        raw = _chat(model, [{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_msg}])
        payload = _parse_json(raw)
        if payload is None:
            raise ValueError("پاسخ مدل JSON معتبر نبود")
        payload = _normalize(payload)

        v = validate_numbers(_all_texts(payload), allowed, raw_values)
        # یک تلاش اصلاحی در صورت وجود عدد ناشناخته
        if v["unknown"]:
            fix = ("این اعداد در بستهٔ واقعیت نبودند: " + "، ".join(v["unknown"][:5])
                   + ". تحلیل را بازنویسی کن و فقط از اعداد بستهٔ واقعیت استفاده کن.")
            raw2 = _chat(model, [{"role": "system", "content": SYSTEM_PROMPT},
                                 {"role": "user", "content": user_msg + "\n\n" + fix}])
            p2 = _parse_json(raw2)
            if p2:
                p2 = _normalize(p2)
                v2 = validate_numbers(_all_texts(p2), allowed, raw_values)
                if len(v2["unknown"]) <= len(v["unknown"]):
                    payload, v = p2, v2
        latency = int((time.time() - t0) * 1000)
        conn.execute(
            "INSERT OR REPLACE INTO ai_analysis(key,scope,model,created,payload,validation,source)"
            " VALUES(?,?,?,?,?,?,?)",
            (key, scope_key, model, datetime.now().isoformat(timespec="seconds"),
             json.dumps(payload, ensure_ascii=False), json.dumps(v, ensure_ascii=False), "ollama"))
        conn.execute("INSERT INTO ai_log(created,model,scope,ok,latency_ms,error) VALUES(?,?,?,?,?,?)",
                     (datetime.now().isoformat(timespec="seconds"), model, scope_key, 1, latency, None))
        return {"status": "ok", "source": "ollama", "model": model,
                "created": datetime.now().isoformat(timespec="seconds"),
                "payload": payload, "validation": v, "latency_ms": latency, "cached": False}
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        conn.execute("INSERT INTO ai_log(created,model,scope,ok,latency_ms,error) VALUES(?,?,?,?,?,?)",
                     (datetime.now().isoformat(timespec="seconds"), model, scope_key, 0,
                      int((time.time() - t0) * 1000), err))
        payload = rules_narrative(bundle, alerts)
        v = validate_numbers(_all_texts(payload), allowed, raw_values)
        return {"status": "fallback", "source": "rules", "model": "قاعده‌محور",
                "created": datetime.now().isoformat(timespec="seconds"),
                "payload": payload, "validation": v, "error": err, "cached": False}


def build_bundle(rows: list[dict], period_label: str, extra=None) -> dict:
    """rows: [{code,title,unit,act,bud,ly}] یا یک ردیف مجتمع."""
    kpis = []
    for r in rows:
        if r.get("act") is None and r.get("bud") is None and r.get("ly") is None:
            continue
        kpis.append({
            "code": r["code"], "title": r["title"], "unit": r["unit"],
            "act": None if r.get("act") is None else round(r["act"], 2),
            "bud": None if r.get("bud") is None else round(r["bud"], 2),
            "ly": None if r.get("ly") is None else round(r["ly"], 2),
        })
    return {"period_label": period_label, "kpis": kpis,
            "extra_numbers": extra or [],
            "dictionary": {
                "واحد پول": "میلیون ریال",
                "مبنای تناژ عملیات": "تخلیه + بارگیری + ترانشیپ + حمل یکسره (روزوب جدا)",
                "مبنای بهره‌وری ناوگان": "فقط ۷۰ دستگاه عملیاتی، تناژ باربری + ترانشیپ",
            }}
