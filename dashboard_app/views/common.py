from __future__ import annotations

import html
from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"],
        [data-testid="stMain"], [data-testid="stSidebar"], [data-testid="stHeader"] {
            direction: rtl !important;
            text-align: right !important;
        }
        [data-testid="stHorizontalBlock"] { direction: rtl; }
        [data-testid="stWidgetLabel"], [data-testid="stMarkdownContainer"],
        [data-testid="stForm"], [data-testid="stRadio"], [data-testid="stCheckbox"],
        [data-testid="stSelectbox"], [data-testid="stTextInput"], [data-testid="stNumberInput"] {
            direction: rtl;
            text-align: right;
        }
        input, textarea { direction: rtl !important; text-align: right !important; }
        [data-baseweb="select"], [data-baseweb="popover"], [data-baseweb="menu"],
        [role="option"] { direction: rtl; text-align: right; }
        [data-baseweb="select"] input { text-align: right !important; }
        .stTabs [data-baseweb="tab-list"] { direction: rtl; }
        .stTabs [data-baseweb="tab"] { direction: rtl; text-align: right; }
        .block-container { max-width: 1480px; padding-top: 1.6rem; padding-bottom: 3rem; }
        [data-testid="stSidebar"] { border-left: 1px solid rgba(54, 92, 84, .12); }
        [data-testid="stMetric"] { direction: rtl; text-align: right; }
        [data-testid="stMetricValue"] { direction: ltr; text-align: right; }
        [data-testid="stPlotlyChart"] { direction: rtl; }
        .stButton > button, .stDownloadButton > button {
            direction: rtl;
            text-align: right;
            border-radius: 10px;
            font-weight: 600;
        }
        .app-kicker { color: #4a746c; font-size: .92rem; margin-bottom: .25rem; }
        .app-title { color: #123d35; font-size: 1.8rem; font-weight: 750; margin: 0 0 .25rem 0; }
        .app-subtitle { color: #647873; margin-top: 0; }
        .sample-note { padding: .8rem 1rem; border-radius: 10px; background: #fff8e8;
                       border: 1px solid #f4dfab; color: #66501b; margin: .5rem 0 1rem; }
        .small-muted { color: #73817e; font-size: .88rem; }
        .rtl-table-wrap { direction: rtl; text-align: right; overflow: auto; width: 100%;
                          border: 1px solid #e1e9e6; border-radius: 10px; background: #fff; }
        table.rtl-table { direction: rtl; text-align: right; border-collapse: collapse;
                          width: max-content; min-width: 100%; font-size: .88rem; }
        table.rtl-table th, table.rtl-table td { direction: rtl; text-align: right;
                          padding: .55rem .7rem; border-bottom: 1px solid #e8eeec;
                          white-space: nowrap; }
        table.rtl-table thead th { position: sticky; top: 0; z-index: 1;
                          color: #183b35; background: #eef4f2; font-weight: 700; }
        table.rtl-table tbody tr:nth-child(even) { background: #fbfcfc; }
        table.rtl-table td span[dir="ltr"] { direction: ltr; unicode-bidi: isolate; display: inline-block; }
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


def render_rtl_table(frame: pd.DataFrame, max_height: int | None = 520) -> None:
    """Render a compact HTML table so Persian headers and cells stay truly RTL."""
    if frame is None or frame.empty:
        st.info("داده‌ای برای نمایش وجود ندارد.")
        return

    columns = list(frame.columns)
    numeric_columns = {
        column: pd.api.types.is_numeric_dtype(frame[column].dtype) for column in columns
    }
    header_html = "".join(
        f'<th scope="col">{html.escape(str(column))}</th>' for column in columns
    )
    body_rows: list[str] = []
    for values in frame.itertuples(index=False, name=None):
        cells: list[str] = []
        for column, value in zip(columns, values):
            missing = value is None
            if not missing:
                try:
                    missing = bool(pd.isna(value))
                except (TypeError, ValueError):
                    missing = False
            if missing:
                content = "—"
            elif numeric_columns[column]:
                rendered = format_number(value, decimals=2)
                if "%" in str(column) and rendered != "—":
                    rendered += "%"
                content = f'<span dir="ltr">{html.escape(rendered)}</span>'
            else:
                content = html.escape(str(value))
            cells.append(f"<td>{content}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    height_style = f"max-height:{int(max_height)}px;" if max_height else ""
    table_html = (
        f'<div class="rtl-table-wrap" style="{height_style}">'
        f'<table class="rtl-table" dir="rtl"><thead><tr>{header_html}</tr></thead>'
        f"<tbody>{''.join(body_rows)}</tbody></table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


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
