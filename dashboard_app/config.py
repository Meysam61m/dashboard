from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
_RUNTIME_DIR = Path(
    os.environ.get("DASHBOARD_DATA_DIR", ROOT_DIR / "instance")
).expanduser()
DB_PATH = (
    Path(
        os.environ.get("DASHBOARD_DB_PATH", _RUNTIME_DIR / "finance_dashboard.sqlite3")
    )
    .expanduser()
    .resolve()
)
DEMO_DATA_PATH = ROOT_DIR / "data" / "demo_records.csv"

APP_TITLE = "داشبورد مالی و عملیاتی لجستیک"
APP_SUBTITLE = "سامانهٔ محلی مدیریت داده‌های عملیاتی، درآمد، هزینه و بودجه"

SECTIONS = ("واردات", "صادرات")
ACTUAL_TYPE = "عملکرد دوره جاری"
BUDGET_TYPE = "بودجه مصوب دوره"
PRIOR_ACTUAL_TYPE = "عملکرد دوره مشابه سال قبل"
RECORD_TYPES = (ACTUAL_TYPE, BUDGET_TYPE, PRIOR_ACTUAL_TYPE)

ROLE_LABELS = {
    "admin": "مدیر",
    "editor": "ثبت‌کننده",
    "viewer": "فقط‌خواندنی",
}
ROLE_CODES = tuple(ROLE_LABELS)
MAX_USERS = 10

JALALI_MONTHS = (
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)
PERIODS = ("سه‌ماههٔ اول", "سه‌ماههٔ دوم", "سه‌ماههٔ سوم", "سه‌ماههٔ چهارم")
PERIOD_FILTERS = ("کل سال", *PERIODS)


def period_for_month(month: int) -> str:
    """Return the Jalali quarter label for a month number (1–12)."""
    if not 1 <= int(month) <= 12:
        raise ValueError("ماه باید بین ۱ و ۱۲ باشد.")
    return PERIODS[(int(month) - 1) // 3]


def months_for_period(period: str) -> list[int]:
    if period == "کل سال":
        return list(range(1, 13))
    try:
        quarter = PERIODS.index(period)
    except ValueError as exc:
        raise ValueError(f"دورهٔ نامعتبر: {period}") from exc
    start = quarter * 3 + 1
    return [start, start + 1, start + 2]


def current_jalali_year() -> int:
    """Use jdatetime when installed; retain a safe fallback for offline installs."""
    try:
        import jdatetime  # type: ignore

        return int(jdatetime.date.today().year)
    except (ImportError, AttributeError, ValueError):
        today = datetime.now(timezone.utc).date()
        # Approximation sufficient for a default value; the user can edit the year.
        return today.year - (622 if today.month < 3 else 621)
