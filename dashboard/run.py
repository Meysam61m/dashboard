"""اجرای داشبورد مدیریتی مجتمع خراسان

    python run.py                 → http://127.0.0.1:8000
    python run.py --port 8080
    python run.py --check         → فقط بررسی، بدون اجرا

اتصال به Ollama روی رایانهٔ دیگر:
    set OLLAMA_HOST=http://192.168.1.10:11434      (ویندوز)
    export OLLAMA_HOST=http://192.168.1.10:11434   (لینوکس/مک)
"""
import argparse
import os
import sys
from pathlib import Path

# خروجی فارسی در کنسول ویندوز
if sys.platform.startswith("win"):
    try:
        os.system("chcp 65001 >nul 2>&1")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

LINE = "─" * 54


def _c(txt, code):
    return f"\033[{code}m{txt}\033[0m" if os.name != "nt" else txt


def check() -> list[tuple[bool, str, str]]:
    """بررسی پیش‌نیازها. خروجی: [(موفق؟, عنوان, توضیح)]"""
    out = []

    # ۱) نسخهٔ پایتون
    v = sys.version_info
    ok = v >= (3, 9)
    out.append((ok, "پایتون", f"{v.major}.{v.minor}.{v.micro}"
                + ("" if ok else " — حداقل ۳٫۹ لازم است")))

    # ۲) بسته‌ها
    need = [("fastapi", "fastapi"), ("uvicorn", "uvicorn"),
            ("httpx", "httpx"), ("openpyxl", "openpyxl"),
            ("multipart", "python-multipart")]
    missing = []
    for mod, pkg in need:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    out.append((not missing, "بسته‌های پایتون",
                "همه نصب‌اند" if not missing else "نصب نیست: " + "، ".join(missing)))

    # ۳) فایل‌های داده
    from app.config import SOURCE_FILES
    absent = [k for k, p in SOURCE_FILES.items() if not Path(p).exists()]
    out.append((not absent, "فایل‌های دادهٔ منبع",
                "هر ۵ فایل موجود است" if not absent
                else "پیدا نشد: " + "، ".join(absent) + " (پوشهٔ data_source را بررسی کنید)"))

    # ۴) فونت
    fonts = list((ROOT / "app" / "static" / "fonts").glob("*.ttf"))
    out.append((len(fonts) >= 3, "فونت وزیرمتن", f"{len(fonts)} فایل"))

    # ۵) Ollama
    try:
        from app import ai
        h = ai.health()
        if h["online"]:
            inst = h.get("installed", {})
            n = sum(1 for x in inst.values() if x)
            fa = "۰۱۲۳۴۵۶۷۸۹"
            n_fa = str(n).translate(str.maketrans("0123456789", fa))
            out.append((True, "Ollama", f"متصل — {n_fa} مدل از ۳ مدل نصب است"))
        else:
            out.append((False, "Ollama",
                        h.get("error_text") or "پاسخ نداد — تحلیل قاعده‌محور فعال می‌ماند"))
    except Exception as e:  # noqa: BLE001
        out.append((False, "Ollama", f"بررسی نشد: {e}"))

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--check", action="store_true", help="فقط بررسی کن و خارج شو")
    a = ap.parse_args()

    from app.config import APP_VERSION, APP_BUILD, OLLAMA_HOST

    print()
    print(LINE)
    print(f"  داشبورد مدیریتی مجتمع خراسان   نسخه {APP_VERSION}")
    print(f"  ساخت {APP_BUILD}   |   کتابخانهٔ برنامه: {ROOT}")
    print(LINE)
    print()

    results = check()
    fatal = False
    for ok, name, detail in results:
        mark = _c("✓", "92") if ok else _c("✗", "91")
        print(f"  {mark} {name:22} {detail}")
        if not ok and name in ("پایتون", "بسته‌های پایتون", "فایل‌های دادهٔ منبع"):
            fatal = True
    print()

    if fatal:
        print(_c("  اجرا ممکن نیست — موارد بالا را برطرف کنید.", "91"))
        print()
        print("  نصب بسته‌ها:   pip install -r requirements.txt")
        print("  بررسی کامل:   python diagnose_ollama.py")
        print()
        return 1

    if a.check:
        print("  بررسی کامل شد. برای اجرا:  python run.py")
        print()
        return 0

    print(f"  آدرس داشبورد: {_c('http://127.0.0.1:' + str(a.port), '96')}")
    print(f"  Ollama:       {OLLAMA_HOST}")
    print("  توقف: Ctrl+C")
    print()

    import webbrowser
    import threading

    def _open():
        import time
        time.sleep(1.8)
        try:
            webbrowser.open(f"http://127.0.0.1:{a.port}")
        except Exception:  # noqa: BLE001
            pass

    if not os.environ.get("NO_BROWSER"):
        threading.Thread(target=_open, daemon=True).start()

    import uvicorn
    uvicorn.run("app.main:app", host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nمتوقف شد.")
