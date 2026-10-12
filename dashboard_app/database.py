from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from dashboard_app.config import DB_PATH

_INIT_LOCK = threading.Lock()
_INITIALIZED_PATH: str | None = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    section     TEXT NOT NULL CHECK (section IN ('واردات', 'صادرات')),
    name        TEXT NOT NULL,
    unit        TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at  TEXT NOT NULL,
    UNIQUE(section, name)
);

CREATE TABLE IF NOT EXISTS records (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    year                  INTEGER NOT NULL CHECK (year BETWEEN 1300 AND 1600),
    month                 INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    period                TEXT NOT NULL,
    service_id            INTEGER NOT NULL REFERENCES services(id),
    record_type           TEXT NOT NULL CHECK (record_type IN (
                              'عملکرد دوره جاری',
                              'بودجه مصوب دوره',
                              'عملکرد دوره مشابه سال قبل'
                          )),
    quantity              REAL NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    revenue_million_rial  REAL NOT NULL DEFAULT 0 CHECK (revenue_million_rial >= 0),
    cost_million_rial     REAL NOT NULL DEFAULT 0 CHECK (cost_million_rial >= 0),
    is_demo               INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    created_by            TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    updated_by            TEXT,
    updated_at            TEXT,
    UNIQUE(year, month, service_id, record_type)
);

CREATE TABLE IF NOT EXISTS users (
    username           TEXT PRIMARY KEY COLLATE NOCASE,
    display_name       TEXT NOT NULL,
    role               TEXT NOT NULL CHECK (role IN ('admin', 'editor', 'viewer')),
    password_salt      TEXT NOT NULL,
    password_hash      TEXT NOT NULL,
    is_active          INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    failed_attempts    INTEGER NOT NULL DEFAULT 0,
    locked_until       TEXT,
    created_by         TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    updated_at         TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    entity      TEXT NOT NULL,
    entity_id   TEXT,
    details     TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_meta (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_records_year_month ON records(year, month);
CREATE INDEX IF NOT EXISTS idx_records_type ON records(record_type);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
"""


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    """Open one short-lived connection to the on-premise SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        str(DB_PATH),
        timeout=25,
        check_same_thread=False,
        isolation_level="DEFERRED",
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 25000")
    connection.execute("PRAGMA synchronous = NORMAL")
    try:
        yield connection
    finally:
        connection.close()


def initialize_db() -> None:
    """Create tables once per process and enable WAL for a single-host LAN deployment."""
    global _INITIALIZED_PATH
    path_key = str(DB_PATH.resolve())
    if _INITIALIZED_PATH == path_key and DB_PATH.exists():
        return
    with _INIT_LOCK:
        if _INITIALIZED_PATH == path_key and DB_PATH.exists():
            return
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with db_connection() as connection:
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            if str(mode).lower() != "wal":
                connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
            connection.commit()
        _INITIALIZED_PATH = path_key


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_audit(
    connection: sqlite3.Connection,
    actor: str,
    action: str,
    entity: str,
    entity_id: str | int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Write a sanitized audit event in the caller's current transaction."""
    connection.execute(
        """INSERT INTO audit_log(actor, action, entity, entity_id, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            actor or "system",
            action,
            entity,
            str(entity_id) if entity_id is not None else None,
            json.dumps(details or {}, ensure_ascii=False, default=str),
            utc_now(),
        ),
    )
