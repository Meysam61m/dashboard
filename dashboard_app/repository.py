from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from dashboard_app.config import RECORD_TYPES, SECTIONS, period_for_month
from dashboard_app.database import db_connection, utc_now, write_audit

_RECORD_SELECT = """
SELECT r.id, r.year, r.month, r.period, s.section, s.name AS service, s.unit,
       r.record_type, r.quantity, r.revenue_million_rial, r.cost_million_rial,
       r.is_demo, r.created_by, r.created_at, r.updated_by, r.updated_at
FROM records AS r
JOIN services AS s ON s.id = r.service_id
"""


def fetch_services(
    section: str | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_inactive:
        clauses.append("is_active = 1")
    if section and section in SECTIONS:
        clauses.append("section = ?")
        params.append(section)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db_connection() as connection:
        rows = connection.execute(
            f"SELECT id, section, name, unit, is_active, created_at FROM services {where} "
            "ORDER BY section, name",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_records(
    *,
    year: int | None = None,
    months: Iterable[int] | None = None,
    section: str | None = None,
    service: str | None = None,
    record_type: str | None = None,
    include_demo: bool = True,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if year is not None:
        clauses.append("r.year = ?")
        params.append(int(year))
    month_values = list(months) if months is not None else []
    if month_values:
        placeholders = ",".join("?" for _ in month_values)
        clauses.append(f"r.month IN ({placeholders})")
        params.extend(int(month) for month in month_values)
    if section and section in SECTIONS:
        clauses.append("s.section = ?")
        params.append(section)
    if service:
        clauses.append("s.name = ?")
        params.append(service)
    if record_type and record_type in RECORD_TYPES:
        clauses.append("r.record_type = ?")
        params.append(record_type)
    if not include_demo:
        clauses.append("r.is_demo = 0")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db_connection() as connection:
        rows = connection.execute(
            _RECORD_SELECT
            + f" {where} ORDER BY r.year, r.month, s.section, s.name, r.record_type",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_record_by_identity(
    year: int,
    month: int,
    section: str,
    service: str,
    record_type: str,
) -> dict[str, Any] | None:
    with db_connection() as connection:
        row = connection.execute(
            _RECORD_SELECT
            + " WHERE r.year = ? AND r.month = ? AND s.section = ? AND s.name = ? AND r.record_type = ?",
            (int(year), int(month), section, service, record_type),
        ).fetchone()
    return dict(row) if row else None


def save_record(
    *,
    year: int,
    month: int,
    section: str,
    service: str,
    record_type: str,
    quantity: float,
    revenue_million_rial: float,
    cost_million_rial: float,
    actor: str,
) -> tuple[int, str]:
    if section not in SECTIONS:
        raise ValueError("بخش باید واردات یا صادرات باشد.")
    if record_type not in RECORD_TYPES:
        raise ValueError("نوع رکورد معتبر نیست.")
    if not 1300 <= int(year) <= 1600:
        raise ValueError("سال باید بین ۱۳۰۰ و ۱۶۰۰ باشد.")
    if not 1 <= int(month) <= 12:
        raise ValueError("ماه باید بین ۱ و ۱۲ باشد.")
    for label, value in (
        ("مقدار عملیاتی", quantity),
        ("درآمد", revenue_million_rial),
        ("هزینه", cost_million_rial),
    ):
        if float(value) < 0:
            raise ValueError(f"{label} نمی‌تواند منفی باشد.")

    now = utc_now()
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        service_row = connection.execute(
            "SELECT id FROM services WHERE section = ? AND name = ? AND is_active = 1",
            (section, service),
        ).fetchone()
        if service_row is None:
            connection.rollback()
            raise ValueError("خدمت انتخاب‌شده فعال نیست یا وجود ندارد.")
        service_id = int(service_row["id"])
        existing = connection.execute(
            """SELECT id, quantity, revenue_million_rial, cost_million_rial,
                      is_demo, created_by
               FROM records
               WHERE year = ? AND month = ? AND service_id = ? AND record_type = ?""",
            (int(year), int(month), service_id, record_type),
        ).fetchone()
        values = {
            "year": int(year),
            "month": int(month),
            "period": period_for_month(int(month)),
            "section": section,
            "service": service,
            "record_type": record_type,
            "quantity": float(quantity),
            "revenue_million_rial": float(revenue_million_rial),
            "cost_million_rial": float(cost_million_rial),
        }
        if existing:
            record_id = int(existing["id"])
            before = {
                "quantity": existing["quantity"],
                "revenue_million_rial": existing["revenue_million_rial"],
                "cost_million_rial": existing["cost_million_rial"],
                "is_demo": bool(existing["is_demo"]),
            }
            connection.execute(
                """UPDATE records
                   SET period = ?, quantity = ?, revenue_million_rial = ?,
                       cost_million_rial = ?, is_demo = 0, updated_by = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    values["period"],
                    values["quantity"],
                    values["revenue_million_rial"],
                    values["cost_million_rial"],
                    actor,
                    now,
                    record_id,
                ),
            )
            write_audit(
                connection,
                actor,
                "update",
                "record",
                record_id,
                {"before": before, "after": values},
            )
            action = "updated"
        else:
            cursor = connection.execute(
                """INSERT INTO records(
                       year, month, period, service_id, record_type, quantity,
                       revenue_million_rial, cost_million_rial, is_demo,
                       created_by, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (
                    values["year"],
                    values["month"],
                    values["period"],
                    service_id,
                    values["record_type"],
                    values["quantity"],
                    values["revenue_million_rial"],
                    values["cost_million_rial"],
                    actor,
                    now,
                ),
            )
            record_id = int(cursor.lastrowid)
            write_audit(connection, actor, "create", "record", record_id, values)
            action = "created"
        connection.commit()
    return record_id, action


def delete_record(record_id: int, actor: str) -> bool:
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            _RECORD_SELECT + " WHERE r.id = ?", (int(record_id),)
        ).fetchone()
        if row is None:
            connection.rollback()
            return False
        write_audit(connection, actor, "delete", "record", record_id, dict(row))
        connection.execute("DELETE FROM records WHERE id = ?", (int(record_id),))
        connection.commit()
    return True


def delete_demo_records(actor: str) -> int:
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        count = int(
            connection.execute(
                "SELECT COUNT(*) FROM records WHERE is_demo = 1"
            ).fetchone()[0]
        )
        connection.execute("DELETE FROM records WHERE is_demo = 1")
        write_audit(
            connection,
            actor,
            "delete_demo_data",
            "records",
            details={"deleted_rows": count},
        )
        connection.commit()
    return count


def add_service(section: str, name: str, unit: str, actor: str) -> int:
    section = section.strip()
    name = name.strip()
    unit = unit.strip()
    if section not in SECTIONS:
        raise ValueError("بخش خدمت باید واردات یا صادرات باشد.")
    if not name or len(name) > 100:
        raise ValueError("نام خدمت را وارد کنید (حداکثر ۱۰۰ نویسه).")
    if not unit or len(unit) > 40:
        raise ValueError("واحد سنجش را وارد کنید (حداکثر ۴۰ نویسه).")
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """INSERT INTO services(section, name, unit, is_active, created_at)
               VALUES (?, ?, ?, 1, ?)""",
            (section, name, unit, utc_now()),
        )
        service_id = int(cursor.lastrowid)
        write_audit(
            connection,
            actor,
            "create",
            "service",
            service_id,
            {"section": section, "name": name, "unit": unit},
        )
        connection.commit()
    return service_id


def update_service(service_id: int, name: str, unit: str, actor: str) -> None:
    name = name.strip()
    unit = unit.strip()
    if not name or len(name) > 100 or not unit or len(unit) > 40:
        raise ValueError("نام خدمت و واحد سنجش معتبر وارد کنید.")
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        before = connection.execute(
            "SELECT section, name, unit FROM services WHERE id = ?", (int(service_id),)
        ).fetchone()
        if before is None:
            connection.rollback()
            raise ValueError("خدمت پیدا نشد.")
        connection.execute(
            "UPDATE services SET name = ?, unit = ? WHERE id = ?",
            (name, unit, int(service_id)),
        )
        write_audit(
            connection,
            actor,
            "update",
            "service",
            service_id,
            {"before": dict(before), "after": {"name": name, "unit": unit}},
        )
        connection.commit()


def set_service_active(service_id: int, active: bool, actor: str) -> None:
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        service = connection.execute(
            "SELECT section, name, is_active FROM services WHERE id = ?",
            (int(service_id),),
        ).fetchone()
        if service is None:
            connection.rollback()
            raise ValueError("خدمت پیدا نشد.")
        connection.execute(
            "UPDATE services SET is_active = ? WHERE id = ?",
            (1 if active else 0, int(service_id)),
        )
        write_audit(
            connection,
            actor,
            "activate" if active else "deactivate",
            "service",
            service_id,
            {"section": service["section"], "name": service["name"]},
        )
        connection.commit()


def fetch_audit_logs(limit: int = 250) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 2000))
    with db_connection() as connection:
        rows = connection.execute(
            """SELECT id, actor, action, entity, entity_id, details, created_at
               FROM audit_log ORDER BY id DESC LIMIT ?""",
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def demo_record_count() -> int:
    with db_connection() as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM records WHERE is_demo = 1"
            ).fetchone()[0]
        )


def database_backup_bytes() -> bytes:
    """Create a consistent SQLite snapshot without copying a live WAL file."""
    with tempfile.TemporaryDirectory(prefix="logistics-dashboard-backup-") as directory:
        backup_path = Path(directory) / "finance_dashboard_backup.sqlite3"
        with db_connection() as source:
            destination = sqlite3.connect(str(backup_path))
            try:
                source.backup(destination)
            finally:
                destination.close()
        return backup_path.read_bytes()
