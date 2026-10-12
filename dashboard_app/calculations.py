from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

import pandas as pd

from dashboard_app.config import (
    ACTUAL_TYPE,
    BUDGET_TYPE,
    JALALI_MONTHS,
    PRIOR_ACTUAL_TYPE,
)

REPORT_COLUMNS = [
    "section",
    "service",
    "unit",
    "prior_quantity",
    "prior_revenue",
    "prior_cost",
    "prior_profit",
    "budget_quantity",
    "budget_revenue",
    "budget_cost",
    "budget_profit",
    "actual_quantity",
    "actual_revenue",
    "actual_cost",
    "actual_profit",
    "quantity_attainment_pct",
    "revenue_attainment_pct",
    "profit_attainment_pct",
    "quantity_variance_vs_prior",
    "revenue_variance_vs_prior",
    "cost_variance_vs_budget",
    "profit_variance_vs_budget",
    "profit_variance_vs_prior",
    "quantity_growth_pct",
    "revenue_growth_pct",
    "cost_growth_pct",
    "profit_growth_pct",
]

DISPLAY_COLUMNS = {
    "section": "بخش",
    "service": "شرح خدمات",
    "unit": "واحد سنجش",
    "prior_quantity": "مقدار عملکرد سال قبل",
    "prior_revenue": "درآمد سال قبل (میلیون ریال)",
    "prior_cost": "هزینه سال قبل (میلیون ریال)",
    "prior_profit": "سود سال قبل (میلیون ریال)",
    "budget_quantity": "بودجه عملیاتی",
    "budget_revenue": "بودجه درآمد (میلیون ریال)",
    "budget_cost": "بودجه هزینه (میلیون ریال)",
    "budget_profit": "سود بودجه (میلیون ریال)",
    "actual_quantity": "مقدار عملکرد جاری",
    "actual_revenue": "درآمد عملکرد (میلیون ریال)",
    "actual_cost": "هزینه عملکرد (میلیون ریال)",
    "actual_profit": "سود عملکرد (میلیون ریال)",
    "quantity_attainment_pct": "تحقق بودجه مقدار (%)",
    "revenue_attainment_pct": "تحقق بودجه درآمد (%)",
    "profit_attainment_pct": "تحقق بودجه سود (%)",
    "quantity_variance_vs_prior": "انحراف مقدار نسبت به سال قبل",
    "revenue_variance_vs_prior": "انحراف درآمد نسبت به سال قبل (میلیون ریال)",
    "cost_variance_vs_budget": "انحراف هزینه از بودجه (میلیون ریال)",
    "profit_variance_vs_budget": "انحراف سود از بودجه (میلیون ریال)",
    "profit_variance_vs_prior": "انحراف سود نسبت به سال قبل (میلیون ریال)",
    "quantity_growth_pct": "رشد مقدار سالانه (%)",
    "revenue_growth_pct": "رشد درآمد سالانه (%)",
    "cost_growth_pct": "رشد هزینه سالانه (%)",
    "profit_growth_pct": "رشد سود سالانه (%)",
}


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _aggregate(
    items: list[dict[str, Any]], field: str, unit: str, service: str
) -> float | None:
    values = [_number(row.get(field)) for row in items]
    values = [value for value in values if value is not None]
    if not values:
        return None
    # Average duration is a monthly average, not a flow that should be summed.
    if field == "quantity" and (unit == "روز" or "میانگین مدت" in service):
        return sum(values) / len(values)
    return sum(values)


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator * 100.0 / denominator


def _growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) * 100.0 / abs(previous)


def _profit(revenue: float | None, cost: float | None) -> float | None:
    if revenue is None or cost is None:
        return None
    return revenue - cost


def build_report(
    records: Iterable[dict[str, Any]],
    report_year: int,
    months: Iterable[int] | None = None,
    section: str | None = None,
    service: str | None = None,
) -> pd.DataFrame:
    """Build the Report_Layout-style table for the selected Jalali period.

    The workbook's `year` is the year in which a record occurred. Current actuals
    and budgets are read from `report_year`; comparable actuals come from the prior
    year. Prior-year records may be marked either as a current actual or as the
    workbook's explicit "comparable period" type; current actual takes precedence
    if both exist for the same service/month.
    """
    selected_months = (
        {int(month) for month in months} if months is not None else set(range(1, 13))
    )
    source = [dict(row) for row in records]
    selected = [
        row
        for row in source
        if int(row.get("month", 0) or 0) in selected_months
        and (section is None or row.get("section") == section)
        and (service is None or row.get("service") == service)
    ]

    grouped: dict[tuple[str, str, str], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"actual": [], "budget": [], "prior": []}
    )
    for row in selected:
        try:
            year = int(row.get("year"))
        except (TypeError, ValueError):
            continue
        kind = row.get("record_type")
        key = (
            str(row.get("section", "")),
            str(row.get("service", "")),
            str(row.get("unit", "")),
        )
        if year == int(report_year) and kind == ACTUAL_TYPE:
            grouped[key]["actual"].append(row)
        elif year == int(report_year) and kind == BUDGET_TYPE:
            grouped[key]["budget"].append(row)
        elif year == int(report_year) - 1 and kind in (ACTUAL_TYPE, PRIOR_ACTUAL_TYPE):
            grouped[key]["prior"].append(row)

    report_rows: list[dict[str, Any]] = []
    for (section_name, service_name, unit), kinds in sorted(grouped.items()):
        # If both historical labels exist, keep the canonical current-actual row
        # for each month and fall back to the explicit prior-period type otherwise.
        prior_by_month: dict[int, dict[str, Any]] = {}
        for row in kinds["prior"]:
            month = int(row["month"])
            current = prior_by_month.get(month)
            if current is None or (
                row.get("record_type") == ACTUAL_TYPE
                and current.get("record_type") != ACTUAL_TYPE
            ):
                prior_by_month[month] = row
        prior_items = list(prior_by_month.values())

        actual_quantity = _aggregate(kinds["actual"], "quantity", unit, service_name)
        actual_revenue = _aggregate(
            kinds["actual"], "revenue_million_rial", unit, service_name
        )
        actual_cost = _aggregate(
            kinds["actual"], "cost_million_rial", unit, service_name
        )
        budget_quantity = _aggregate(kinds["budget"], "quantity", unit, service_name)
        budget_revenue = _aggregate(
            kinds["budget"], "revenue_million_rial", unit, service_name
        )
        budget_cost = _aggregate(
            kinds["budget"], "cost_million_rial", unit, service_name
        )
        prior_quantity = _aggregate(prior_items, "quantity", unit, service_name)
        prior_revenue = _aggregate(
            prior_items, "revenue_million_rial", unit, service_name
        )
        prior_cost = _aggregate(prior_items, "cost_million_rial", unit, service_name)

        actual_profit = _profit(actual_revenue, actual_cost)
        budget_profit = _profit(budget_revenue, budget_cost)
        prior_profit = _profit(prior_revenue, prior_cost)
        report_rows.append(
            {
                "section": section_name,
                "service": service_name,
                "unit": unit,
                "prior_quantity": prior_quantity,
                "prior_revenue": prior_revenue,
                "prior_cost": prior_cost,
                "prior_profit": prior_profit,
                "budget_quantity": budget_quantity,
                "budget_revenue": budget_revenue,
                "budget_cost": budget_cost,
                "budget_profit": budget_profit,
                "actual_quantity": actual_quantity,
                "actual_revenue": actual_revenue,
                "actual_cost": actual_cost,
                "actual_profit": actual_profit,
                "quantity_attainment_pct": _safe_ratio(
                    actual_quantity, budget_quantity
                ),
                "revenue_attainment_pct": _safe_ratio(actual_revenue, budget_revenue),
                "profit_attainment_pct": _safe_ratio(actual_profit, budget_profit),
                "quantity_variance_vs_prior": (
                    actual_quantity - prior_quantity
                    if actual_quantity is not None and prior_quantity is not None
                    else None
                ),
                "revenue_variance_vs_prior": (
                    actual_revenue - prior_revenue
                    if actual_revenue is not None and prior_revenue is not None
                    else None
                ),
                "cost_variance_vs_budget": (
                    actual_cost - budget_cost
                    if actual_cost is not None and budget_cost is not None
                    else None
                ),
                "profit_variance_vs_budget": (
                    actual_profit - budget_profit
                    if actual_profit is not None and budget_profit is not None
                    else None
                ),
                "profit_variance_vs_prior": (
                    actual_profit - prior_profit
                    if actual_profit is not None and prior_profit is not None
                    else None
                ),
                "quantity_growth_pct": _growth(actual_quantity, prior_quantity),
                "revenue_growth_pct": _growth(actual_revenue, prior_revenue),
                "cost_growth_pct": _growth(actual_cost, prior_cost),
                "profit_growth_pct": _growth(actual_profit, prior_profit),
            }
        )

    if not report_rows:
        return pd.DataFrame(columns=REPORT_COLUMNS)
    return pd.DataFrame(report_rows, columns=REPORT_COLUMNS)


def report_for_display(report: pd.DataFrame) -> pd.DataFrame:
    """Rename report columns for the Persian UI while preserving numeric values."""
    return report.rename(columns=DISPLAY_COLUMNS)


def monthly_totals(
    records: Iterable[dict[str, Any]],
    report_year: int,
    months: Iterable[int],
    section: str | None = None,
    service: str | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for month in months:
        report = build_report(records, report_year, [month], section, service)
        rows.append(
            {
                "ماه": JALALI_MONTHS[int(month) - 1],
                "شماره ماه": month,
                "درآمد عملکرد": _sum_column(report, "actual_revenue"),
                "بودجه درآمد": _sum_column(report, "budget_revenue"),
                "سود عملکرد": _sum_column(report, "actual_profit"),
                "سود بودجه": _sum_column(report, "budget_profit"),
            }
        )
    return pd.DataFrame(rows)


def _sum_column(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return 0.0
    values = [_number(value) for value in frame[column].tolist()]
    return sum(value for value in values if value is not None)
