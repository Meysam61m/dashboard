#!/usr/bin/env python3
"""
عیب‌یاب اتصال Ollama
====================
این فایل را روی همان رایانه‌ای اجرا کنید که Ollama نصب است:

    python diagnose_ollama.py

هیچ چیزی نصب یا تغییر نمی‌دهد؛ فقط گزارش می‌دهد.
"""
import json
import os
import shutil
import socket
import sys
import time

CANDIDATES = [
    "http://127.0.0.1:11434",
    "http://localhost:11434",
    "http://[::1]:11434",
]
NEEDED = ["qwen3.5:4b", "qwen3.5:9b"]

BAR = "─" * 62


def ok(msg):    print(f"  \033[92m✓\033[0m {msg}")
def bad(msg):   print(f"  \033[91m✗\033[0m {msg}")
def warn(msg):  print(f"  \033[93m!\033[0m {msg}")
def head(msg):  print(f"\n{BAR}\n{msg}\n{BAR}")


def port_open(host: str, port: int = 11434, timeout: float = 2.0) -> bool:
    """آزمون در سطح TCP — مستقل از HTTP و پروکسی."""
    try:
        fam = socket.AF_INET6 if ":" in host else socket.AF_INET
        with socket.socket(fam, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host.strip("[]"), port)) == 0
    except OSError:
        return False


def http_probe(url: str):
    """آزمون HTTP با trust_env=False تا پروکسی سیستم دخالت نکند."""
    try:
        import httpx
    except ImportError:
        return None, "بستهٔ httpx نصب نیست — اجرا کنید: pip install httpx"
    try:
        t0 = time.time()
        r = httpx.get(f"{url}/api/tags", timeout=5.0, trust_env=False)
        ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        models = [m.get("name") or m.get("model") for m in r.json().get("models", [])]
        return (ms, [m for m in models if m]), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def http_probe_via_proxy(url: str):
    """آزمون دومی که پروکسی سیستم را رعایت می‌کند — برای نشان دادن تفاوت."""
    proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
             or os.environ.get("ALL_PROXY") or os.environ.get("https_proxy")
             or os.environ.get("all_proxy"))
    if not proxy:
        return None, "پروکسی تنظیم نشده"
    try:
        import httpx
        r = httpx.get(f"{url}/api/tags", timeout=5.0, trust_env=True)
        return ("متصل شد" if r.status_code == 200 else f"HTTP {r.status_code}"), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}"


def main() -> int:
    print("\n\033[1mعیب‌یاب اتصال Ollama — داشبورد مدیریتی مجتمع خراسان\033[0m")
    print(f"پایتون {sys.version.split()[0]} | سیستم {sys.platform}")

    # ۱) نصب Ollama
    head("۱) نصب و اجرای Ollama")
    exe = shutil.which("ollama")
    if exe:
        ok(f"فرمان ollama پیدا شد: {exe}")
    elif sys.platform.startswith("win"):
        p = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
        if os.path.exists(p):
            ok(f"Ollama در مسیر پیش‌فرض ویندوز پیدا شد: {p}")
        else:
            bad("فرمان ollama پیدا نشد — از ollama.com نصب کنید")

    # ۲) پورت
    head("۲) آیا سرویس روی پورت ١١۴۳۴ گوش می‌دهد؟")
    listening = {}
    for h in ("127.0.0.1", "::1"):
        listening[h] = port_open(h)
        (ok if listening[h] else bad)(f"{h}:11434 → {'باز است' if listening[h] else 'بسته است'}")
    if not any(listening.values()):
        bad("سرویس اجرا نشده. Ollama را از منوی استارت (یا ollama serve) اجرا کنید.")
        return 1

    # ۳) HTTP
    head("۳) پاسخ HTTP")
    working = None
    for url in CANDIDATES:
        res, err = http_probe(url)
        if res:
            ms, models = res
            ok(f"{url} → {ms} میلی‌ثانیه، {len(models)} مدل")
            working = working or url
        else:
            bad(f"{url} → {err}")

    # ۴) پروکسی — شایع‌ترین علت «مرورگر می‌بیند، برنامه نمی‌بیند»
    head("۴) پروکسی سیستم")
    proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
             or os.environ.get("ALL_PROXY") or os.environ.get("https_proxy")
             or os.environ.get("all_proxy"))
    if not proxy:
        ok("هیچ متغیر پروکسی‌ای در محیط تنظیم نیست")
    else:
        warn(f"پروکسی فعال است: {proxy}")
        if working:
            before = http_probe(working)
            after, err = http_probe_via_proxy(working)
            if before[0] and after is None:
                bad("با فعال بودن پروکسی، اتصال به Ollama قطع می‌شود → همین علت مشکل است")
                print("\n     \033[1mراه‌حل:\033[0m نسخهٔ ۱٫۱ برنامه این را خودکار دور می‌زند.")
                print("     در نسخه‌های قدیمی، متغیرهای پروکسی را موقتاً خالی کنید:")
                if sys.platform.startswith("win"):
                    print('       set HTTP_PROXY=\n       set HTTPS_PROXY=\n       python run.py')
                else:
                    print("       env -u HTTP_PROXY -u HTTPS_PROXY python3 run.py")
            else:
                ok("پروکسی مانع اتصال نیست")

    # ۵) مدل‌ها
    head("۵) مدل‌های لازم")
    if not working:
        bad("اتصال برقرار نشد؛ فهرست مدل‌ها خوانده نشد")
        return 1
    res, _ = http_probe(working)
    models = res[1]
    if not models:
        bad("هیچ مدلی نصب نیست")
    else:
        ok(f"{len(models)} مدل نصب است:")
        for m in models:
            print(f"       • {m}")
    print()
    for need in NEEDED:
        have = [m for m in models if m == need]
        if have:
            ok(f"{need} موجود است" + (f" (به‌صورت {have[0]})" if have[0] != need else ""))
        else:
            bad(f"{need} نصب نیست → ollama pull {need}")

    # ۶) آزمون واقعی تولید متن
    head("۶) آزمون واقعی تولید متن (مسیر /api/chat)")
    test_model = next((n for n in NEEDED if n in models), None) or (models[0] if models else None)
    if not test_model:
        bad("مدلی برای آزمون نیست")
    else:
        try:
            import httpx
            print(f"  در حال پرسش از «{test_model}» (تا ۹۰ ثانیه)…")
            t0 = time.time()
            r = httpx.post(f"{working}/api/chat", timeout=90.0, trust_env=False, json={
                "model": test_model, "stream": False,
                "messages": [{"role": "user", "content": "فقط بنویس: آماده"}],
                "options": {"num_predict": 8, "num_ctx": 512},
            })
            dt = time.time() - t0
            if r.status_code == 200:
                txt = (r.json().get("message") or {}).get("content", "").strip()
                ok(f"پاسخ در {dt:.1f} ثانیه: «{txt[:40]}»")
                tok = r.json().get("eval_count")
                if tok and dt > 0:
                    ok(f"سرعت تقریبی: {tok / dt:.1f} توکن بر ثانیه")
            elif r.status_code == 404:
                try:
                    msg = r.json().get("error", "")
                except Exception:  # noqa: BLE001
                    msg = r.text[:100]
                bad(f"کد ۴۰۴ — {msg or 'مسیر /api/chat یافت نشد'}")
                if "model" in str(msg).lower():
                    print("     یعنی: این مدل نصب نیست → ollama pull " + test_model)
                else:
                    print("     یعنی: نسخهٔ Ollama قدیمی است و /api/chat ندارد.")
                    print("     راه‌حل: Ollama را به‌روزرسانی کنید (ollama.com/download)")
            else:
                bad(f"کد {r.status_code}: {r.text[:150]}")
        except Exception as e:  # noqa: BLE001
            bad(f"{type(e).__name__}: {str(e)[:120]}")

    # ۷) نتیجه
    head("نتیجه")
    missing = [n for n in NEEDED if n not in models]
    if missing:
        print(f"  \033[93mاین مدل‌ها نصب نیستند:\033[0m {', '.join(missing)}")
        for m in missing:
            print(f"     ollama pull {m}")
        print("\n  بدون این مدل‌ها داشبورد کار می‌کند و تحلیل قاعده‌محور می‌دهد،")
        print("  ولی تحلیل هوشمند با مدل زبانی انجام نمی‌شود.")
        return 0
    print("  \033[92mهمه‌چیز آماده است.\033[0m برنامه را اجرا کنید:  python run.py")
    return 0
    print("  \033[93mموارد بالا را برطرف کنید، سپس دوباره این فایل را اجرا کنید.\033[0m")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nمتوقف شد.")
