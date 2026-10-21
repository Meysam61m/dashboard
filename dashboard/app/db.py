"""طرح پایگاه داده — داده خام، شاخص محاسبه‌شده، تحلیل کش‌شده و نسخه‌ها."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS dim_branch (
    name      TEXT PRIMARY KEY,
    province  TEXT DEFAULT '',
    is_border INTEGER DEFAULT 0,
    active    INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS dim_metric (
    code      TEXT PRIMARY KEY,
    title     TEXT NOT NULL,
    domain    TEXT NOT NULL,
    unit      TEXT NOT NULL,
    direction TEXT NOT NULL,          -- up | down | target | flat
    formula   TEXT NOT NULL,
    decimals  INTEGER DEFAULT 0
);

-- تنها جایی که داده وارد می‌شود
CREATE TABLE IF NOT EXISTS fact (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    branch    TEXT NOT NULL,
    year      INTEGER NOT NULL,
    period    TEXT NOT NULL,          -- H1 | H2 | Y
    code      TEXT NOT NULL,
    month     INTEGER DEFAULT 0,      -- 0 = جمع دوره، 1..6 = ماه
    scenario  TEXT NOT NULL,          -- ACT | BUD | LY
    value     REAL,
    version   INTEGER NOT NULL DEFAULT 1,
    UNIQUE(branch, year, period, code, month, scenario)
);

CREATE INDEX IF NOT EXISTS ix_fact_lookup ON fact(year, period, branch, code, scenario);

-- شاخص محاسبه‌شده (بازسازی خودکار؛ دستی ویرایش نمی‌شود)
CREATE TABLE IF NOT EXISTS kpi (
    branch    TEXT NOT NULL,
    year      INTEGER NOT NULL,
    period    TEXT NOT NULL,
    code      TEXT NOT NULL,
    act       REAL,
    bud       REAL,
    ly        REAL,
    PRIMARY KEY (branch, year, period, code)
);

CREATE TABLE IF NOT EXISTS project (
    pid       TEXT PRIMARY KEY,
    branch    TEXT NOT NULL,
    title     TEXT NOT NULL,
    domain    TEXT DEFAULT '',
    total     REAL DEFAULT 0,
    bud6      REAL DEFAULT 0,
    act       REAL DEFAULT 0,
    prog      REAL DEFAULT 0,
    months    INTEGER DEFAULT 0,
    start     INTEGER DEFAULT 0,
    year      INTEGER NOT NULL,
    period    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS data_version (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    created   TEXT NOT NULL,
    author    TEXT DEFAULT '',
    note      TEXT DEFAULT '',
    n_facts   INTEGER DEFAULT 0,
    locked    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ai_analysis (
    key       TEXT PRIMARY KEY,        -- hash(scope + data_version + model + prompt_version)
    scope     TEXT NOT NULL,
    model     TEXT NOT NULL,
    created   TEXT NOT NULL,
    payload   TEXT NOT NULL,           -- JSON خروجی مدل
    validation TEXT NOT NULL,          -- JSON نتیجه اعتبارسنجی عددی
    source    TEXT NOT NULL            -- ollama | rules
);

CREATE TABLE IF NOT EXISTS ai_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    created   TEXT NOT NULL,
    model     TEXT,
    scope     TEXT,
    ok        INTEGER,
    latency_ms INTEGER,
    error     TEXT
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript(SCHEMA)


def current_version(conn) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id),0) AS v FROM data_version").fetchone()
    return int(row["v"])


def new_version(conn, author: str = "سیستم", note: str = "") -> int:
    from datetime import datetime
    n = conn.execute("SELECT COUNT(*) c FROM fact").fetchone()["c"]
    cur = conn.execute(
        "INSERT INTO data_version(created, author, note, n_facts) VALUES(?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), author, note, n),
    )
    return int(cur.lastrowid)
