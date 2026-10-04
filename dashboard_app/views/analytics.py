from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard_app.calculations import (
    build_report,
    monthly_totals,
    report_for_display,
)
from dashboard_app.config import (
    ACTUAL_TYPE,
    BUDGET_TYPE,
    PERIOD_FILTERS,
    SECTIONS,
    current_jalali_year,
    months_for_period,
)
from dashboard_app.repository import fetch_records, fetch_services
from dashboard_app.views.common import (
    download_table_buttons,
    format_number,
    format_percent,
    page_heading,
    render_rtl_table,
)

ALL_SECTIONS = "همهٔ بخش‌ها"
ALL_SERVICES = "همهٔ خدمات"


def _number_sum(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame:
        return None
    values = pd.to_numeric(frame[column], errors="coerce")
    if not values.notna().any():
        return None
    return float(values.sum(min_count=1))


def _filters(
    records: list[dict[str, Any]], key_prefix: str
) -> tuple[int, list[int], str | None, str | None, str]:
    report_years = sorted(
        {
            int(row["year"])
            for row in records
            if row.get("record_type") in (ACTUAL_TYPE, BUDGET_TYPE)
        }
    )
    if not report_years:
        report_years = sorted({int(row["year"]) for row in records})
    if not report_years:
        report_years = [current_jalali_year()]
    default_year = max(report_years)

    first, second, third, fourth = st.columns([1, 1, 1, 1.35])
    with first:
        year = st.selectbox(
            "سال گزارش (شمسی)",
            report_years,
            index=report_years.index(default_year),
            key=f"{key_prefix}_year",
        )
    with second:
        period = st.selectbox(
            "دورهٔ گزارش", PERIOD_FILTERS, index=1, key=f"{key_prefix}_period"
        )
    with third:
        section_option = st.selectbox(
            "بخش", [ALL_SECTIONS, *SECTIONS], key=f"{key_prefix}_section"
        )
    section = None if section_option == ALL_SECTIONS else section_option
    catalog = fetch_services(section=section)
    service_names = sorted({item["name"] for item in catalog})
    with fourth:
        service_option = st.selectbox(
            "خدمت", [ALL_SERVICES, *service_names], key=f"{key_prefix}_service"
        )
    service = None if service_option == ALL_SERVICES else service_option
    return int(year), months_for_period(period), section, service, period


def _show_sample_notice(records: list[dict[str, Any]]) -> None:
    demo_count = sum(1 for row in records if bool(row.get("is_demo")))
    if demo_count:
        st.markdown(
            f'<div class="sample-note"><strong>دادهٔ نمونه:</strong> این پایگاه داده شامل {demo_count:,} ردیف ساختگی است. '
            "هزینه‌های نمونه نیز به‌صورت مصنوعی تولید شده‌اند و برای تصمیم‌گیری واقعی مالی مناسب نیستند.</div>",
            unsafe_allow_html=True,
        )


def _style_figure(figure: go.Figure, title: str) -> go.Figure:
    figure.update_layout(
        title=title,
        title_x=1,
        title_xanchor="right",
        font={"family": "Tahoma, Arial, sans-serif", "size": 13},
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin={"l": 20, "r": 20, "t": 55, "b": 50},
        legend={
            "orientation": "h",
            "y": 1.12,
            "x": 1,
            "xanchor": "right",
            "traceorder": "reversed",
        },
        xaxis={"tickangle": -25, "gridcolor": "#eef2f1", "autorange": "reversed"},
        yaxis={"gridcolor": "#eef2f1"},
    )
    return figure


def _render_charts(
    report: pd.DataFrame,
    records: list[dict[str, Any]],
    year: int,
    months: list[int],
    section: str | None,
    service: str | None,
) -> None:
    if report.empty:
        st.info("برای این انتخاب هنوز داده‌ای ثبت نشده است.")
        return

    chart_columns = st.columns(2)
    with chart_columns[0]:
        chart_data = report[
            ["section", "service", "actual_revenue", "budget_revenue"]
        ].copy()
        chart_data["service_label"] = (
            chart_data["section"] + " · " + chart_data["service"]
        )
        chart_data = chart_data[["service_label", "actual_revenue", "budget_revenue"]]
        chart_data = chart_data.rename(
            columns={
                "actual_revenue": "درآمد عملکرد",
                "budget_revenue": "بودجه درآمد",
            }
        )
        chart_long = chart_data.melt(
            id_vars="service_label", var_name="شاخص", value_name="میلیون ریال"
        )
        chart_long["میلیون ریال"] = pd.to_numeric(
            chart_long["میلیون ریال"], errors="coerce"
        ).fillna(0)
        figure = px.bar(
            chart_long,
            x="service_label",
            y="میلیون ریال",
            color="شاخص",
            barmode="group",
            color_discrete_sequence=["#2c8073", "#9bb8b1"],
        )
        _style_figure(figure, "مقایسهٔ درآمد عملکرد و بودجه")
        st.plotly_chart(figure, width="stretch")

    with chart_columns[1]:
        profit_data = report[
            ["section", "service", "actual_profit", "budget_profit"]
        ].copy()
        profit_data["service_label"] = (
            profit_data["section"] + " · " + profit_data["service"]
        )
        profit_data = profit_data[["service_label", "actual_profit", "budget_profit"]]
        profit_data = profit_data.rename(
            columns={
                "actual_profit": "سود عملکرد",
                "budget_profit": "سود بودجه",
            }
        )
        profit_long = profit_data.melt(
            id_vars="service_label", var_name="شاخص", value_name="میلیون ریال"
        )
        profit_long["میلیون ریال"] = pd.to_numeric(
            profit_long["میلیون ریال"], errors="coerce"
        ).fillna(0)
        figure = px.bar(
            profit_long,
            x="service_label",
            y="میلیون ریال",
            color="شاخص",
            barmode="group",
            color_discrete_sequence=["#d58a36", "#e9c99e"],
        )
        _style_figure(figure, "مقایسهٔ سود عملکرد و سود بودجه")
        st.plotly_chart(figure, width="stretch")

    selected_months = [
        month
        for month in months
        if any(
            int(row.get("year", 0)) == year
            and int(row.get("month", 0)) == month
            and row.get("record_type") in (ACTUAL_TYPE, BUDGET_TYPE)
            and (section is None or row.get("section") == section)
            and (service is None or row.get("service") == service)
            for row in records
        )
    ]
    if selected_months:
        monthly = monthly_totals(records, year, selected_months, section, service)
        figure = go.Figure()
        figure.add_bar(
            x=monthly["ماه"],
            y=monthly["درآمد عملکرد"],
            name="درآمد عملکرد",
            marker_color="#2c8073",
        )
        figure.add_bar(
            x=monthly["ماه"],
            y=monthly["بودجه درآمد"],
            name="بودجه درآمد",
            marker_color="#a8c2bc",
        )
        figure.add_scatter(
            x=monthly["ماه"],
            y=monthly["سود عملکرد"],
            name="سود عملکرد",
            mode="lines+markers",
            yaxis="y2",
            line={"color": "#d58a36", "width": 3},
        )
        figure.update_layout(
            barmode="group",
            yaxis={"title": "درآمد (میلیون ریال)", "gridcolor": "#eef2f1"},
            yaxis2={
                "title": "سود (میلیون ریال)",
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
            },
        )
        _style_figure(figure, "روند ماهانهٔ درآمد، بودجه و سود")
        st.plotly_chart(figure, width="stretch")


def render_dashboard() -> None:
    page_heading(
        "داشبورد تحلیلی",
        "نمایی سریع از عملکرد، بودجه، درآمد، هزینه و سود در دورهٔ انتخاب‌شده.",
    )
    records = fetch_records()
    _show_sample_notice(records)
    year, months, section, service, period = _filters(records, "dashboard")
    report = build_report(records, year, months, section, service)
    st.caption(f"سال شمسی {year} · {period} · مبالغ مالی به میلیون ریال هستند.")

    actual_revenue = _number_sum(report, "actual_revenue")
    budget_revenue = _number_sum(report, "budget_revenue")
    actual_cost = _number_sum(report, "actual_cost")
    actual_profit = _number_sum(report, "actual_profit")
    budget_profit = _number_sum(report, "budget_profit")
    revenue_attainment = (
        (actual_revenue * 100 / budget_revenue)
        if actual_revenue is not None and budget_revenue
        else None
    )
    profit_attainment = (
        (actual_profit * 100 / budget_profit)
        if actual_profit is not None and budget_profit
        else None
    )

    metrics = st.columns(5)
    metrics[0].metric("درآمد عملکرد", format_number(actual_revenue), "میلیون ریال")
    metrics[1].metric("تحقق بودجهٔ درآمد", format_percent(revenue_attainment))
    metrics[2].metric("هزینهٔ عملکرد", format_number(actual_cost), "میلیون ریال")
    profit_delta = None
    if actual_profit is not None and budget_profit is not None:
        profit_delta = (
            f"{format_number(actual_profit - budget_profit)} م.ر نسبت به بودجه"
        )
    metrics[3].metric("سود عملکرد", format_number(actual_profit), profit_delta)
    metrics[4].metric("تحقق بودجهٔ سود", format_percent(profit_attainment))

    if report.empty:
        st.info(
            "برای این سال و دوره داده‌ای وجود ندارد. از بخش «ثبت داده‌ها» اطلاعات را وارد کنید."
        )
        return
    st.divider()
    _render_charts(report, records, year, months, section, service)
    with st.expander("پیش‌نمایش گزارش", expanded=False):
        display = report_for_display(report)
        render_rtl_table(display, max_height=380)


def render_final_report() -> None:
    page_heading(
        "گزارش نهایی",
        "چیدمان نزدیک به شیت گزارش اکسل، همراه با محاسبات هزینه و سود. مبالغ درآمد و هزینه به میلیون ریال هستند.",
    )
    records = fetch_records()
    _show_sample_notice(records)
    year, months, section, service, period = _filters(records, "report")
    report = build_report(records, year, months, section, service)
    st.caption(
        f"سال شمسی {year} · {period} · مقایسه با عملکرد دورهٔ مشابه سال {year - 1}."
    )
    if report.empty:
        st.info("برای ساخت گزارش، ابتدا دادهٔ عملکرد یا بودجه ثبت کنید.")
        return

    display = report_for_display(report)
    render_rtl_table(display, max_height=600)
    stem = f"گزارش_لجستیک_{year}_{period.replace(' ', '_')}"
    download_table_buttons(display, stem, "final_report")
    st.caption(
        "تحقق بودجه = عملکرد ÷ بودجه × ۱۰۰. انحراف سالانه = عملکرد دورهٔ جاری − عملکرد دورهٔ مشابه سال قبل. "
        "در صورت صفر بودن مخرج، درصد به‌صورت خالی نمایش داده می‌شود."
    )
