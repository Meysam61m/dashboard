from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st

ROLE_NAMES = {"admin": "مدیر", "editor": "ثبت‌کننده", "viewer": "فقط‌خواندنی"}


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
            direction: rtl;
            text-align: right;
        }
        .block-container { max-width: 1480px; padding-top: 1.6rem; padding-bottom: 3rem; }
        [data-testid="stSidebar"] { border-left: 1px solid rgba(54, 92, 84, .12); }
        [data-testid="stMetric"] { direction: rtl; text-align: right; }
        [data-testid="stMetricValue"] { direction: ltr; text-align: right; }
        [data-testid="stDataFrame"] { direction: rtl; }
        .stButton > button, .stDownloadButton > button {
            border-radius: 10px;
            font-weight: 600;
        }
        .app-kicker { color: #4a746c; font-size: .92rem; margin-bottom: .25rem; }
        .app-title { color: #123d35; font-size: 1.8rem; font-weight: 750; margin: 0 0 .25rem 0; }
        .app-subtitle { color: #647873; margin-top: 0; }
        .sample-note { padding: .8rem 1rem; border-radius: 10px; background: #fff8e8;
                       border: 1px solid #f4dfab; color: #66501b; margin: .5rem 0 1rem; }
        .small-muted { color: #73817e; font-size: .88rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_heading(title: str, subtitle: str | None = None) -> None:
    st.markdown(
        f'<div class="app-kicker">سامانهٔ محلی لجستیک</div><h1 class="app-title">{title}</h1>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(f'<p class="app-subtitle">{subtitle}</p>', unsafe_allow_html=True)


def format_number(value: Any, decimals: int = 1) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if pd.isna(number):
        return "—"
    rendered = f"{number:,.{decimals}f}"
    if decimals:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def format_percent(value: Any) -> str:
    rendered = format_number(value, 1)
    return "—" if rendered == "—" else f"{rendered}%"


def download_table_buttons(
    frame: pd.DataFrame, file_stem: str, key_prefix: str
) -> None:
    if frame is None or frame.empty:
        return
    csv_data = frame.to_csv(index=False).encode("utf-8-sig")
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="گزارش")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "دریافت CSV",
            data=csv_data,
            file_name=f"{file_stem}.csv",
            mime="text/csv; charset=utf-8",
            key=f"{key_prefix}_csv_download",
        )
    with col2:
        st.download_button(
            "دریافت Excel",
            data=excel_buffer.getvalue(),
            file_name=f"{file_stem}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_xlsx_download",
        )
