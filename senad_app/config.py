"""تنظیمات و مسیرهای برنامه."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = Path(os.environ.get("SENAD_INSTANCE_DIR", BASE_DIR / "instance"))
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("SENAD_DB_PATH", INSTANCE_DIR / "senad.db"))
BACKUP_DIR = Path(os.environ.get("SENAD_BACKUP_DIR", INSTANCE_DIR / "backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
LOGO_PATH = INSTANCE_DIR / "logo.png"

MAX_ITEMS = 15  # حداکثر ردیف هر سند (چاپ یک‌صفحه‌ای)

ROLES = {
    "admin": "مدیر سیستم",
    "supervisor": "سرپرست / مالی",
    "karperdaz": "کارپرداز",
    "viewer": "ناظر (فقط‌خواندنی)",
}

DEFAULT_SETTINGS = {
    "company_name": "شرکت انبارهای عمومی و خدمات گمرکی ایران",
    "complex_name": "مجتمع خراسان",
    "national_id": "10100351070",
    "economic_code": "411111361641",
    "doc_title": "سند هزینه شعبه",
    "doc_control": "GEN/FI/MH/01",
    "doc_control_date": "1398/04/26",
    "standard_text": "کلیه موارد فوق با رعایت صرفه و صلاح شرکت و با کمترین بهای ممکن و بهترین کیفیت انجام گرفت.",
    "number_separator": "-",
    "seq_width": "4",
    "tanakhah_alert": "200000000",
}

# مجوزها: نقش → مجموعه عملیات مجاز
PERMISSIONS = {
    "admin": {"create", "edit_draft", "edit_final", "finalize", "void", "tanakhah",
              "manage_users", "manage_branches", "manage_settings", "backup", "view_log", "view_all"},
    "supervisor": {"create", "edit_draft", "edit_final", "finalize", "void", "tanakhah",
                   "view_log", "view_all"},
    "karperdaz": {"create", "edit_draft", "finalize"},
    "viewer": set(),
}


def can(role: str, action: str) -> bool:
    return action in PERMISSIONS.get(role, set())
