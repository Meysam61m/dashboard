from __future__ import annotations

import csv
from pathlib import Path

from dashboard_app.config import DEMO_DATA_PATH, period_for_month
from dashboard_app.database import db_connection, utc_now, write_audit

DEMO_DATA_VERSION = "2"


def seed_demo_data(path: Path = DEMO_DATA_PATH) -> int:
    """Load or upgrade the fictional sample set without overwriting user-entered rows."""
    if not path.exists():
        raise FileNotFoundError(f"فایل دادهٔ نمونه پیدا نشد: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    inserted = 0
    now = utc_now()
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        version_row = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'demo_data_version'"
        ).fetchone()
        if version_row is not None and version_row["value"] == DEMO_DATA_VERSION:
            connection.commit()
            return 0

        seeded_before = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'demo_data_seeded'"
        ).fetchone()
        previous_demo_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM records WHERE is_demo = 1"
            ).fetchone()[0]
        )
        if seeded_before is not None and previous_demo_count == 0:
            # Respect an administrator's previous decision to clear all demo rows.
            connection.execute(
                """INSERT INTO app_meta(key, value) VALUES ('demo_data_version', ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (DEMO_DATA_VERSION,),
            )
            connection.commit()
            return 0

        if seeded_before is not None:
            # Upgrade old seeded examples, while preserving any rows an operator edited
            # (editing a sample changes is_demo to 0).
            connection.execute("DELETE FROM records WHERE is_demo = 1")

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

        for key, value in (
            ("demo_data_seeded", "1"),
            ("demo_data_version", DEMO_DATA_VERSION),
        ):
            connection.execute(
                """INSERT INTO app_meta(key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, value),
            )
        write_audit(
            connection,
            "system",
            "seed_demo_data" if seeded_before is None else "upgrade_demo_data",
            "records",
            details={
                "inserted_rows": inserted,
                "replaced_demo_rows": previous_demo_count
                if seeded_before is not None
                else 0,
                "version": DEMO_DATA_VERSION,
                "source": path.name,
                "synthetic_costs": True,
            },
        )
        connection.commit()
    return inserted
