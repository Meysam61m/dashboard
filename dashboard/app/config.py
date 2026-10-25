"""تنظیمات مرکزی برنامه."""
# ══════════════════════════════════════════════
#  نسخهٔ برنامه — تنها منبع حقیقت
#  این عدد در رابط کاربری، API و عیب‌یاب نمایش داده می‌شود.
# ══════════════════════════════════════════════
APP_VERSION = "2.2.0"
APP_BUILD = "1405-07-29"

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent                      # پوشهٔ dashboard
DB_PATH = Path(os.environ.get("DASH_DB", ROOT_DIR / "data" / "dashboard.db"))

# اتصال به Ollama — روی همان رایانه‌ای که برنامه اجرا می‌شود
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "300"))

# مدل‌ها بر اساس سخت‌افزار CPU-only تعریف شده‌اند
MODEL_CHAT = os.environ.get("MODEL_CHAT", "qwen3.5:4b")
MODEL_ANALYSIS = os.environ.get("MODEL_ANALYSIS", "qwen3.5:9b")
MODEL_DEEP = os.environ.get("MODEL_DEEP", "gemma4:12b")

# سقف خروجی هر تحلیل (به دلیل سرعت پایین CPU)
AI_MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", "900"))

# مدل بعد از هر تحلیل چند دقیقه در حافظه بماند؟
# روی CPU، بارگذاری دوبارهٔ مدل ۹b حدود ۳۰ تا ۶۰ ثانیه طول می‌کشد.
# با نگه داشتن مدل، تحلیل‌های بعدی سریع‌تر شروع می‌شوند.
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
AI_TEMPERATURE = 0.2

DEFAULT_YEAR = 1405
DEFAULT_PERIOD = "H1"
PERIOD_LABEL = {"H1": "شش‌ماهه نخست", "H2": "شش‌ماهه دوم", "Y": "سالانه"}


def _find(name: str) -> Path:
    """جست‌وجوی فایل داده در چند مسیر ممکن — تا برنامه در هر ساختاری اجرا شود."""
    candidates = [
        ROOT_DIR / "data_source" / name,      # داخل مخزن
        ROOT_DIR.parent / name,               # کنار پوشهٔ dashboard
        ROOT_DIR / name,
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


# داده‌های خام موجود که در آغاز برنامه درون‌ریزی می‌شوند
SOURCE_FILES = {
    "real_all": _find("real_all.json"),
    "ops3": _find("ops3.json"),
    "mod": _find("mod.json"),
    "staff": _find("staff.json"),
    "fuel": _find("fuel_repair.json"),
}
