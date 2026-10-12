"""اتصال و ساختار پایگاه داده (SQLite)."""
import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS user_branch (
    user_id INTEGER NOT NULL,
    branch_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, branch_id)
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_number TEXT UNIQUE,
    branch_id INTEGER NOT NULL,
    doc_year INTEGER,
    seq INTEGER,
    doc_date TEXT NOT NULL,
    date_key INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    finalized_at TEXT, finalized_by INTEGER,
    updated_at TEXT, updated_by INTEGER,
    voided_at TEXT, voided_by INTEGER, void_reason TEXT DEFAULT '',
    print_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS doc_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL,
    row_no INTEGER NOT NULL,
    item_date TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    insurance REAL NOT NULL DEFAULT 0,
    tax REAL NOT NULL DEFAULT 0,
    amount REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tanakhah_tx (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id INTEGER NOT NULL,
    tx_date TEXT NOT NULL,
    date_key INTEGER NOT NULL,
    amount REAL NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS branch_seq (
    branch_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    last_seq INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (branch_id, year)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    entity TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_documents_branch ON documents(branch_id, date_key);
CREATE INDEX IF NOT EXISTS idx_items_doc ON doc_items(doc_id);
CREATE INDEX IF NOT EXISTS idx_tanakhah_branch ON tanakhah_tx(branch_id, date_key);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for key, value in config.DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value)
            )


def get_setting(key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
