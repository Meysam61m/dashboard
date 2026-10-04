from __future__ import annotations

import csv
from pathlib import Path

from dashboard_app.config import DEMO_DATA_PATH, period_for_month
from dashboard_app.database import db_connection, utc_now, write_audit


def seed_demo_data(path: Path = DEMO_DATA_PATH) -> int:
    """Load the supplied fictional template rows once, including clearly synthetic costs."""
    if not path.exists():
        raise FileNotFoundError(f"فایل دادهٔ نمونه پیدا نشد: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    inserted = 0
    now = utc_now()
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        seeded = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'demo_data_seeded'"
        ).fetchone()
        if seeded is not None:
            connection.commit()
            return 0

        # Seed lookup values first; the two permitted departments are explicit.
        for row in rows:
            section = row["section"].strip()
            if section not in ("واردات", "صادرات"):
                continue
            connection.execute(
                """INSERT INTO services(section, name, unit, is_active, created_at)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(section, name) DO NOTHING""",
                (section, row["service"].strip(), row["unit"].strip(), now),
            )

        for row in rows:
            section = row["section"].strip()
            if section not in ("واردات", "صادرات"):
                continue
            service = connection.execute(
                "SELECT id FROM services WHERE section = ? AND name = ?",
                (section, row["service"].strip()),
            ).fetchone()
            if service is None:
                continue
            cursor = connection.execute(
                """INSERT INTO records(
                       year, month, period, service_id, record_type, quantity,
                       revenue_million_rial, cost_million_rial, is_demo,
                       created_by, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'system', ?)
                   ON CONFLICT(year, month, service_id, record_type) DO NOTHING""",
                (
                    int(row["year"]),
                    int(row["month"]),
                    period_for_month(int(row["month"])),
                    int(service["id"]),
                    row["record_type"].strip(),
                    float(row["quantity"] or 0),
                    float(row["revenue_million_rial"] or 0),
                    float(row["cost_million_rial"] or 0),
                    now,
                ),
            )
            inserted += cursor.rowcount

        connection.execute(
            "INSERT INTO app_meta(key, value) VALUES ('demo_data_seeded', '1')"
        )
        write_audit(
            connection,
            "system",
            "seed_demo_data",
            "records",
            details={
                "inserted_rows": inserted,
                "source": path.name,
                "synthetic_costs": True,
            },
        )
        connection.commit()
    return inserted
