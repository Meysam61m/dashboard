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

import json as _j
import socket as _socket
import urllib.error as _urlerr
import urllib.request as _urlreq

from . import catalog
from .config import (APP_VERSION, APP_BUILD, AI_MAX_TOKENS, AI_TEMPERATURE, OLLAMA_KEEP_ALIVE, MODEL_ANALYSIS, MODEL_CHAT,
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
حداکثر ۲ یافته، ۲ عامل، ۲ ریسک و ۲ اقدام بنویس. هر رشته حداکثر ۱۵ کلمه.
پاسخ باید با { شروع شود و با } تمام شود. هیچ متنی پیش یا پس از JSON ننویس."""


SHORT_PROMPT = """تو تحلیل‌گر مالی و عملیاتی مجتمع انبارهای عمومی خراسان هستی.
فقط بر پایهٔ «بستهٔ واقعیت» بنویس. هیچ عددی که در بسته نیست ننویس. هیچ محاسبهٔ تازه‌ای نکن.

کوتاه بنویس، مثل یک پیام مدیر به مدیر:
- headline: یک جمله، حداکثر ۱۸ کلمه
- findings: حداکثر ۱ مورد
- drivers، risks، actions: هر کدام حداکثر ۱ مورد
- data_gaps: حداکثر ۱ مورد
هر رشته حداکثر ۱۲ کلمه. پاسخ فقط JSON، بدون متن اضافه، بدون بلوک کد."""


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


# ── لایهٔ HTTP بدون وابستگی خارجی
# از کتابخانهٔ استاندارد پایتون استفاده می‌کنیم تا نصب برنامه به httpx
# نیاز نداشته باشد. ProxyHandler({}) معادل trust_env=False است:
# پروکسی سیستم نادیده گرفته می‌شود، چون درخواست ما به localhost است.
_OPENER = _urlreq.build_opener(_urlreq.ProxyHandler({}))


def _http(url: str, body: dict | None = None, timeout: float = 30.0):
    """درخواست JSON. خروجی: (کد وضعیت، متن پاسخ)"""
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = _j.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = _urlreq.Request(url, data=data, headers=headers,
                          method="POST" if body is not None else "GET")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return getattr(r, "status", 200), r.read().decode("utf-8", "replace")
    except _urlerr.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except _socket.timeout:
        raise TimeoutError("پاسخ در زمان مقرر نرسید") from None
    except _urlerr.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, _socket.timeout):
            raise TimeoutError("پاسخ در زمان مقرر نرسید") from None
        raise ConnectionError(str(reason)) from None


def _json_or_none(txt: str):
    try:
        return _j.loads(txt)
    except Exception:  # noqa: BLE001
        return None


# ── اتصال
# نکتهٔ مهم: trust_env=False
# کتابخانه‌های HTTP معمول (httpx، requests) متغیرهای HTTP_PROXY / ALL_PROXY سیستم را
# رعایت می‌کنند و درخواست به 127.0.0.1 را هم از پروکسی عبور می‌دهند — همان چیزی که
# باعث می‌شود مرورگر Ollama را ببیند ولی برنامه نبیند. ProxyHandler({}) این را خنثی می‌کند.
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


_MODELS_CACHE: list[str] | None = None
_MODELS_AT: float = 0.0
_MODELS_TTL = 30.0          # فهرست مدل‌ها بیش از ۳۰ ثانیه کهنه نمی‌ماند


def known_models(refresh: bool = False) -> list[str]:
    """فهرست مدل‌های نصب‌شده.

    نکتهٔ مهم: نتیجهٔ خالی کش نمی‌شود. اگر Ollama هنوز بالا نیامده باشد،
    کشِ خالی باعث می‌شد برنامه تا ابد مدل اشتباه انتخاب کند.
    """
    global _MODELS_CACHE, _MODELS_AT
    stale = (time.time() - _MODELS_AT) > _MODELS_TTL
    if refresh or _MODELS_CACHE is None or stale:
        h = health()
        got = h.get("models") or []
        if got:                       # فقط نتیجهٔ موفق کش می‌شود
            _MODELS_CACHE = got
            _MODELS_AT = time.time()
        elif _MODELS_CACHE is None:
            _MODELS_CACHE = []
    return _MODELS_CACHE or []


def pick_model(want: str, refresh: bool = False) -> tuple[str, bool]:
    """اگر مدل درخواستی نصب نباشد، بهترین مدلِ موجود به‌جایش برگردانده می‌شود.
    خروجی: (مدل انتخابی، آیا جایگزین شده)"""
    names = known_models(refresh=refresh)
    if not names:
        names = known_models(refresh=True)
    if not names or _has_model(names, want):
        return want, False
    for alt in (MODEL_ANALYSIS, MODEL_CHAT, MODEL_DEEP):
        if _has_model(names, alt):
            return alt, alt != want
    return names[0], names[0] != want


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
        code, txt = _http(f"{url.rstrip('/')}/api/tags", timeout=4.0)
        if code >= 400:
            return False, 0, [], f"HTTP {code}: {txt[:120]}"
        ms = int((time.time() - t0) * 1000)
        data = _json_or_none(txt) or {}
        models = [m.get("name") or m.get("model") for m in data.get("models", [])]
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
            globals()["_MODELS_CACHE"] = names
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


def ps() -> list[dict]:
    """مدل‌هایی که همین حالا در حافظه بارگذاری شده‌اند."""
    try:
        code, txt = _http(f"{host()}/api/ps", timeout=5.0)
        if code >= 400:
            return []
        out = []
        for m in (_json_or_none(txt) or {}).get("models", []):
            size = m.get("size") or 0
            out.append({
                "name": m.get("name") or m.get("model"),
                "size_gb": round(size / (1024 ** 3), 1) if size else None,
                "until": m.get("expires_at"),
            })
        return out
    except Exception:  # noqa: BLE001
        return []


def warmup(model: str | None = None) -> dict:
    """مدل را در حافظه بارگذاری می‌کند تا اولین تحلیل معطل نماند."""
    want = model or MODEL_ANALYSIS
    m, _ = pick_model(want)
    t0 = time.time()
    try:
        code, txt = _http(f"{host()}/api/chat", {
            "model": m, "stream": False, "keep_alive": OLLAMA_KEEP_ALIVE,
            "messages": [{"role": "user", "content": "سلام"}],
            "options": {"num_predict": 1, "num_ctx": 512},
        }, timeout=OLLAMA_TIMEOUT)
        if code >= 400:
            return {"ok": False, "model": m, "error": _body_error(code, txt)}
        return {"ok": True, "model": m, "seconds": round(time.time() - t0, 1),
                "keep_alive": OLLAMA_KEEP_ALIVE, "loaded": ps()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "model": m, "error": f"{type(e).__name__}: {e}"}


def selftest(model: str | None = None) -> dict:
    """آزمون گام‌به‌گام با زمان هر مرحله. دقیقاً می‌گوید کجا شکست خورد."""
    steps = []

    def step(name, ok, ms, detail=""):
        steps.append({"name": name, "ok": ok, "ms": int(ms), "detail": detail})
        return ok

    t = time.time()
    ok_tcp = False
    try:
        hp = host().split("//")[-1].split(":")
        h_ = hp[0]
        p_ = int(hp[1]) if len(hp) > 1 else 11434
        with _socket.create_connection((h_, p_), timeout=3):
            ok_tcp = True
        step("۱. پورت باز است", True, (time.time() - t) * 1000, f"{h_}:{p_}")
    except Exception as e:  # noqa: BLE001
        step("۱. پورت باز است", False, (time.time() - t) * 1000, f"{type(e).__name__}: {e}")
        return {"ok": False, "steps": steps}

    t = time.time()
    try:
        code, txt = _http(f"{host()}/api/tags", timeout=6)
        names = [m.get("name") for m in (_json_or_none(txt) or {}).get("models", [])]
        step("۲. سرویس پاسخ می‌دهد", code == 200, (time.time() - t) * 1000,
             f"HTTP {code} — {len(names)} مدل")
    except Exception as e:  # noqa: BLE001
        step("۲. سرویس پاسخ می‌دهد", False, (time.time() - t) * 1000, f"{type(e).__name__}: {e}")
        return {"ok": False, "steps": steps}

    t = time.time()
    want = model or MODEL_ANALYSIS
    used, subbed = pick_model(want, refresh=True)
    exists = _has_model(names, used)
    step("۳. انتخاب مدل", exists, (time.time() - t) * 1000,
         f"{used}" + (f" (به‌جای {want})" if subbed else ""))
    if not exists:
        return {"ok": False, "steps": steps,
                "hint": f"هیچ مدلی نصب نیست. اجرا کنید: ollama pull {MODEL_ANALYSIS}"}

    # ۴) پرسش بدون جریان
    t = time.time()
    try:
        out = _chat(used, [{"role": "user", "content": "فقط بنویس: سلام"}],
                    max_tokens=16, json_mode=False)
        ok4 = bool(out.strip())
        step("۴. پاسخ ساده (بدون جریان)", ok4, (time.time() - t) * 1000,
             f"«{out.strip()[:60]}»" if ok4 else "پاسخ خالی برگشت")
    except Exception as e:  # noqa: BLE001
        step("۴. پاسخ ساده (بدون جریان)", False, (time.time() - t) * 1000,
             f"{type(e).__name__}: {str(e)[:160]}")
        return {"ok": False, "steps": steps, "model": used}

    # ۵) پرسش با جریان
    t = time.time()
    got = ""
    first_ms = 0
    err = ""
    try:
        for kind, val in _chat_stream(used, [{"role": "user", "content": "فقط بنویس: سلام"}],
                                      max_tokens=16):
            if kind == "توکن":
                if not got:
                    first_ms = int((time.time() - t) * 1000)
                got += val
            elif kind == "خطا":
                err = str(val)
                break
            elif kind == "پایان":
                break
        step("۵. پاسخ با جریان", bool(got) and not err, (time.time() - t) * 1000,
             f"{len(got)} نویسه، اولین در {first_ms} میلی‌ثانیه" if got else (err or "چیزی نرسید"))
    except Exception as e:  # noqa: BLE001
        step("۵. پاسخ با جریان", False, (time.time() - t) * 1000, f"{type(e).__name__}: {e}")

    return {"ok": all(x["ok"] for x in steps), "model": used,
            "substituted_from": want if subbed else None, "steps": steps}


def diag() -> dict:
    """گزارش کامل وضعیت — همان چیزی که diagnose_ollama.py می‌گوید، از داخل برنامه."""
    import platform
    import sys as _sys

    h = health()
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    # ۱) سرویس
    add("سرویس Ollama", h["online"],
        f"پاسخ در {h.get('latency_ms')} میلی‌ثانیه" if h["online"]
        else (h.get("error_text") or "پاسخ نداد"))

    # ۲) نشانی
    add("نشانی", True,
        f"{h.get('host')}" + (" (جایگزین خودکار)" if h.get("switched") else ""))

    # ۳) پروکسی
    import os as _os
    px = (_os.environ.get("HTTPS_PROXY") or _os.environ.get("HTTP_PROXY")
          or _os.environ.get("ALL_PROXY") or _os.environ.get("https_proxy"))
    add("پروکسی سیستم", True,
        f"فعال است ({px}) — ولی نادیده گرفته می‌شود" if px else "تنظیم نشده")

    # ۴) مدل‌ها — «تحلیل» الزامی است؛ دو مدل دیگر اختیاری
    names = h.get("models") or []
    for role, want, required in (("تحلیل", MODEL_ANALYSIS, True),
                                 ("گفت‌وگو", MODEL_CHAT, False),
                                 ("عمیق", MODEL_DEEP, False)):
        have = _has_model(names, want)
        if have:
            add(f"مدل {role} ({want})", True, "نصب است")
        elif required:
            add(f"مدل {role} ({want})", False, f"نصب نیست — ollama pull {want}")
        else:
            # اختیاری: نبودنش مانع کار نیست، پس علامت هشدار نه خطا
            checks.append({
                "name": f"مدل {role} ({want})", "ok": True, "optional": True,
                "detail": f"نصب نیست — اختیاری. اگر خواستید: ollama pull {want}",
            })

    # ۵) آزمون واقعی
    real = {"ok": False, "text": "انجام نشد"}
    if h["online"] and names:
        model, _ = pick_model(MODEL_ANALYSIS)
        try:
            t0 = time.time()
            out = _chat(model, [{"role": "user", "content": "فقط بنویس: آماده"}], max_tokens=8)
            dt = time.time() - t0
            real = {"ok": True, "model": model, "seconds": round(dt, 1),
                    "text": (out or "").strip()[:40] or "(خالی)"}
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            real = {"ok": False, "text": msg}

    return {
        "app_version": APP_VERSION, "app_build": APP_BUILD,
        "python": _sys.version.split()[0], "platform": platform.platform(terse=True),
        "ollama": {k: h.get(k) for k in
                   ("online", "host", "host_configured", "switched", "latency_ms",
                    "error", "error_text", "models", "installed", "remote_backend")},
        "checks": checks, "real_test": real,
        "available": {
            "chat": _has_model(names, MODEL_CHAT),
            "analysis": _has_model(names, MODEL_ANALYSIS),
            "deep": _has_model(names, MODEL_DEEP),
        },
        "loaded": ps(),
        "keep_alive": OLLAMA_KEEP_ALIVE,
    }


def _body_error(code: int, txt: str) -> str:
    """پیام خطای Ollama از بدنهٔ پاسخ."""
    j = _json_or_none(txt)
    if isinstance(j, dict) and j.get("error"):
        return str(j["error"])[:300]
    return (txt or "")[:300] or f"HTTP {code}"


def _chat(model: str, messages: list[dict], max_tokens: int = AI_MAX_TOKENS,
          meta: dict | None = None, json_mode: bool = True) -> str:
    """متن پاسخ. اگر meta داده شود، علت پایان تولید (length = بریدگی) در آن نوشته می‌شود."""
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": AI_TEMPERATURE,
            "num_predict": max_tokens,
            "num_ctx": 8192,          # پنجرهٔ کوچک: روی CPU سریع‌تر و کم‌مصرف‌تر
            "top_p": 0.9,
        },
    }
    if json_mode:
        body["format"] = "json"
    code, txt = _http(f"{host()}/api/chat", body, timeout=OLLAMA_TIMEOUT)
    if code == 404:
        detail = _body_error(code, txt)
        # سرویس قدیمی که /api/chat ندارد → مسیر قدیمی
        if "model" not in detail.lower():
            return _generate(model, messages, body["options"])
        # مدل نصب نیست: فهرست را تازه کن و با مدلِ موجود یک‌بار دیگر تلاش کن
        alt, changed = pick_model(model, refresh=True)
        if changed and alt != model:
            body["model"] = alt
            code, txt = _http(f"{host()}/api/chat", body, timeout=OLLAMA_TIMEOUT)
            if code < 400:
                data = _json_or_none(txt) or {}
                if meta is not None:
                    meta["done_reason"] = data.get("done_reason") or ""
                    meta["eval_count"] = data.get("eval_count")
                    meta["model_used"] = alt
                return (data.get("message") or {}).get("content", "") or ""
            detail = _body_error(code, txt)
        raise RuntimeError(f"مدل «{model}» روی این Ollama نصب نیست. "
                           f"اجرا کنید: ollama pull {model} — پاسخ Ollama: {detail[:120]}")
    if code >= 400:
        raise RuntimeError(f"Ollama کد {code} داد: {_body_error(code, txt)}")
    data = _json_or_none(txt) or {}
    if meta is not None:
        meta["done_reason"] = data.get("done_reason") or ""
        meta["eval_count"] = data.get("eval_count")
    return (data.get("message") or {}).get("content", "") or ""


def _chat_stream(model: str, messages: list[dict], max_tokens: int = 700):
    """جریان تدریجی پاسخ. رویدادها: («توکن», متن) / («پایان», meta) / («خطا», پیام)."""
    body = {
        "model": model, "messages": messages, "stream": True,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0.3, "num_predict": max_tokens, "num_ctx": 8192},
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = _urlreq.Request(f"{host()}/api/chat", data=data, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8", "Accept": "application/x-ndjson"})

    t0 = time.time()
    first = None
    n_tok = 0
    try:
        try:
            resp = _OPENER.open(req, timeout=OLLAMA_TIMEOUT)
        except _urlerr.HTTPError as e:
            body_txt = e.read().decode("utf-8", "replace")
            detail = _body_error(e.code, body_txt)
            if e.code == 404 and "model" in detail.lower():
                # همان باگ: مدل درخواستی نصب نیست → با فهرست تازه مدل دیگری بردار
                alt, changed = pick_model(model, refresh=True)
                if changed and alt != model:
                    body["model"] = alt
                    req = _urlreq.Request(
                        f"{host()}/api/chat",
                        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                        method="POST", headers={
                            "Content-Type": "application/json; charset=utf-8",
                            "Accept": "application/x-ndjson"})
                    yield ("نکته", f"مدل «{model}» نصب نبود؛ با «{alt}» پاسخ می‌دهم.")
                    resp = _OPENER.open(req, timeout=OLLAMA_TIMEOUT)
                else:
                    yield ("خطا", f"مدل «{model}» نصب نیست و جایگزینی پیدا نشد. "
                                  f"اجرا کنید: ollama pull {model}")
                    return
            else:
                yield ("خطا", f"Ollama کد {e.code}: {detail[:200]}")
                return
        with resp as r:
            for line in r:
                line = line.strip()
                if not line:
                    continue
                j = _json_or_none(line.decode("utf-8", "replace"))
                if not j:
                    continue
                if j.get("error"):
                    yield ("خطا", str(j["error"]))
                    return
                piece = (j.get("message") or {}).get("content", "")
                if piece:
                    if first is None:
                        first = (time.time() - t0) * 1000
                    n_tok += 1
                    yield ("توکن", piece)
                if j.get("done"):
                    el = time.time() - t0
                    yield ("پایان", {
                        "model": model,
                        "seconds": round(el, 1),
                        "first_ms": int(first or 0),
                        "tokens": j.get("eval_count") or n_tok,
                        "tps": round((j.get("eval_count") or n_tok) / el, 1) if el > 0 else None,
                        "done_reason": j.get("done_reason"),
                    })
                    return
        yield ("پایان", {"model": model, "seconds": round(time.time() - t0, 1), "tokens": n_tok})
    except _urlerr.HTTPError as e:
        yield ("خطا", _body_error(e.code, e.read().decode("utf-8", "replace")))
    except TimeoutError:
        yield ("خطا", "پاسخ در زمان مقرر نرسید — مدل مشغول بارگذاری است یا صفحه شلوغ است")
    except Exception as e:  # noqa: BLE001
        yield ("خطا", f"{type(e).__name__}: {e}")


def _generate(model: str, messages: list[dict], options: dict) -> str:
    """مسیر جایگزین برای نسخه‌های قدیمی Ollama که /api/chat ندارند."""
    sys_part = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    usr_part = "\n\n".join(m["content"] for m in messages if m["role"] == "user")
    code, txt = _http(f"{host()}/api/generate", {
        "model": model, "prompt": usr_part, "system": sys_part,
        "stream": False, "format": "json", "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": options,
    }, timeout=OLLAMA_TIMEOUT)
    if code >= 400:
        raise RuntimeError(f"Ollama کد {code} داد: {_body_error(code, txt)}")
    return (_json_or_none(txt) or {}).get("response", "") or ""


def _close_truncated(txt: str) -> str:
    """JSON نیمه‌تمام را می‌بندد: رشتهٔ باز را تمام و آکولادهای باز را می‌بندد."""
    out = []
    stack = []          # آکولادها و براکت‌های باز
    in_str = False
    esc = False
    for ch in txt:
        out.append(ch)
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
    if in_str:
        out.append('"')
    # حذف عضو نیمه‌تمام انتهایی مثل  ,"risks":  یا  ,"risks": [
    body = "".join(out).rstrip()
    body = re.sub(r',\s*"[^"]*"\s*:\s*$', "", body)          # ,"key":
    body = re.sub(r',\s*$', "", body)                          # ویرگول انتهایی
    body = re.sub(r'"\s*:\s*$', "", body)                     # "key":
    for closer in reversed(stack):
        body += closer
    return body


def _parse_json(txt: str):
    """تجزیهٔ JSON با تحمل خطا: حذف بلوک کد، نقل‌قول‌های فارسی، ویرگول اضافه،
    و ترمیم پاسخِ نیمه‌تمام."""
    if not txt or not txt.strip():
        return None
    t = txt.strip()

    # بلوک کد
    t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    t = t.strip()

    # نقل‌قول‌های تایپوگرافی
    t = (t.replace("\u201c", '"').replace("\u201d", '"')
          .replace("\u00ab", '"').replace("\u00bb", '"')
          .replace("\u2018", "'").replace("\u2019", "'"))

    for candidate in (t, _slice_object(t), _close_truncated(t), _close_truncated(_slice_object(t))):
        if not candidate:
            continue
        c = candidate.strip()
        c = re.sub(r",\s*([}\]])", r"\1", c)          # ویرگول پیش از بستن
        try:
            v = json.loads(c)
            if isinstance(v, dict):
                return v
        except json.JSONDecodeError:
            continue
    return None


def _slice_object(t: str) -> str:
    """از اولین آکولاد تا آخرین آکولاد — برای وقتی مدل متن اضافه نوشته."""
    i = t.find("{")
    j = t.rfind("}")
    if i >= 0 and j > i:
        return t[i:j + 1]
    if i >= 0:
        return t[i:]
    return ""


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

    model_requested = model or MODEL_ANALYSIS
    model, substituted = pick_model(model_requested)
    model_notice = (f"مدل «{model_requested}» نصب نیست؛ تحلیل با «{model}» انجام شد."
                    if substituted else None)
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
        meta: dict = {}
        raw = _chat(model, [{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_msg}], meta=meta)
        payload = _parse_json(raw)

        # تلاش دوم: پاسخ ناقص بود یا JSON خراب درآمد
        if payload is None:
            note = ("پاسخ قبلی ناقص بود و کامل نشد. " if meta.get("done_reason") == "length"
                    else "پاسخ قبلی JSON معتبر نبود. ")
            raw_meta: dict = {}
            raw = _chat(model, [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": (raw or "")[:1500]},
                {"role": "user", "content":
                    note + "فقط یک شیء JSON معتبر و کامل بنویس. کوتاه: حداکثر ۲ مورد در هر فهرست. "
                           "بدون هیچ متن اضافه."},
            ], max_tokens=min(1200, AI_MAX_TOKENS + 300), meta=raw_meta)
            payload = _parse_json(raw)
            meta = raw_meta

        if payload is None:
            raise ValueError("پاسخ مدل JSON معتبر نبود"
                             + (f" (پاسخ خام: {raw[:200]}…)" if raw else ""))
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
                "model_requested": model_requested, "model_notice": model_notice,
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
                "model_requested": model_requested, "model_notice": model_notice,
                "raw_excerpt": (raw or "")[:400] or None,
                "created": datetime.now().isoformat(timespec="seconds"),
                "payload": payload, "validation": v, "error": err, "cached": False}


def quick(conn, scope_key: str, scope_label: str, bundle: dict,
          model: str | None = None, focus: str | None = None) -> dict:
    """تحلیل کوتاه یک‌شات: یک تیتر و چند نکته. برای تحلیل بخشی (مثلاً فقط ناوگان)."""
    from .db import current_version

    want = model or MODEL_ANALYSIS
    used, subbed = pick_model(want)
    notice = (f"مدل «{want}» نصب نیست؛ با «{used}» انجام شد." if subbed else None)

    vals = [v for k in bundle.get("kpis", [])
            for v in (k.get("act"), k.get("bud"), k.get("ly"))] + list(bundle.get("extra_numbers", []))
    allowed = _fmt_set(vals)

    user = (f"دامنه: {scope_label}\nدوره: {bundle.get('period_label')}\n\n"
            "بستهٔ واقعیت (تنها منبع مجاز اعداد):\n"
            + json.dumps(bundle, ensure_ascii=False)
            + "\n\nتحلیل کوتاه را در قالب JSON بنویس.")

    t0 = time.time()
    raw = ""
    try:
        meta: dict = {}
        raw = _chat(used, [{"role": "system", "content": SHORT_PROMPT},
                           {"role": "user", "content": user}], max_tokens=420, meta=meta)
        payload = _parse_json(raw)
        if payload is None and meta.get("done_reason") == "length":
            raw = _chat(used, [{"role": "system", "content": SHORT_PROMPT},
                               {"role": "user", "content": user + "\nفقط یک جمله بنویس."}],
                        max_tokens=260, meta=meta)
            payload = _parse_json(raw)
        if payload is None:
            raise ValueError("پاسخ مدل JSON معتبر نبود")
        payload = _normalize(payload)
        v = validate_numbers(_all_texts(payload), allowed, vals)
        return {"status": "ok", "source": "ollama", "model": used,
                "model_requested": want, "model_notice": notice, "mode": "quick",
                "focus": focus, "created": datetime.now().isoformat(timespec="seconds"),
                "payload": payload, "validation": v, "raw": raw[:600],
                "latency_ms": int((time.time() - t0) * 1000), "cached": False}
    except Exception as e:  # noqa: BLE001
        payload = rules_narrative(bundle, [])
        v = validate_numbers(_all_texts(payload), allowed, vals)
        return {"status": "fallback", "source": "rules", "model": "قاعده‌محور",
                "model_requested": want, "model_notice": notice, "mode": "quick",
                "focus": focus, "created": datetime.now().isoformat(timespec="seconds"),
                "payload": payload, "validation": v, "raw": raw[:600] or None,
                "error": f"{type(e).__name__}: {e}",
                "latency_ms": int((time.time() - t0) * 1000), "cached": False}


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
