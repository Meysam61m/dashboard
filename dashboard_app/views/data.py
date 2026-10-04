from __future__ import annotations

import sqlite3
from typing import Any

import pandas as pd
import streamlit as st

from dashboard_app.config import (
    JALALI_MONTHS,
    RECORD_TYPES,
    SECTIONS,
    current_jalali_year,
    period_for_month,
)
from dashboard_app.repository import (
    add_service,
    delete_demo_records,
    delete_record,
    demo_record_count,
    fetch_record_by_identity,
    fetch_records,
    fetch_services,
    save_record,
    set_service_active,
    update_service,
)
from dashboard_app.views.common import (
    download_table_buttons,
    page_heading,
)

RECORD_DISPLAY = {
    "year": "سال شمسی",
    "month": "ماه شماره",
    "period": "دوره",
    "section": "بخش",
    "service": "شرح خدمت",
    "unit": "واحد سنجش",
    "record_type": "نوع رکورد",
    "quantity": "مقدار عملیاتی",
    "revenue_million_rial": "درآمد (میلیون ریال)",
    "cost_million_rial": "هزینه (میلیون ریال)",
    "is_demo": "دادهٔ نمونه؟",
    "created_by": "ثبت‌کننده",
    "created_at": "زمان ثبت (UTC)",
    "updated_by": "آخرین ویرایشگر",
    "updated_at": "زمان ویرایش (UTC)",
}


def render_data_management(user: dict[str, str]) -> None:
    page_heading(
        "ثبت و مدیریت داده‌ها",
        "هر ردیف نمایندهٔ یک خدمت در یک ماه و یک نوع رکورد است؛ ثبت دوبارهٔ همان ترکیب، رکورد موجود را به‌روزرسانی می‌کند.",
    )
    can_edit = user["role"] in ("admin", "editor")
    if not can_edit:
        st.warning("حساب شما فقط اجازهٔ مشاهده دارد.")
        return
    tab_entry, tab_records, tab_services = st.tabs(
        ["ثبت / ویرایش", "جست‌وجو و خروجی", "فهرست خدمات"]
    )
    with tab_entry:
        _entry_tab(user)
    with tab_records:
        _records_tab(user)
    with tab_services:
        _services_tab(user)


def _entry_tab(user: dict[str, str]) -> None:
    st.subheader("ورود اطلاعات خام")
    active_services = fetch_services()
    if not active_services:
        st.warning("فهرست خدمات خالی است؛ مدیر باید ابتدا خدمت تعریف کند.")
        return

    section = st.selectbox("بخش", SECTIONS, key="entry_section")
    section_services = [item for item in active_services if item["section"] == section]
    if not section_services:
        st.info("برای این بخش هنوز خدمتی تعریف نشده است.")
        return
    service_options = [item["name"] for item in section_services]
    service_name = st.selectbox("نوع خدمت", service_options, key="entry_service")
    service_meta = next(
        item for item in section_services if item["name"] == service_name
    )

    years = [int(row["year"]) for row in fetch_records()]
    default_year = (
        max([current_jalali_year(), *years]) if years else current_jalali_year()
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        year = int(
            st.number_input(
                "سال شمسی داده",
                min_value=1300,
                max_value=1600,
                value=default_year,
                step=1,
                key="entry_year",
            )
        )
    with col2:
        month_name = st.selectbox("ماه", JALALI_MONTHS, index=0, key="entry_month")
        month = JALALI_MONTHS.index(month_name) + 1
    with col3:
        record_type = st.selectbox("نوع رکورد", RECORD_TYPES, key="entry_record_type")
    period = period_for_month(month)
    st.caption(
        f"دوره به‌صورت خودکار از ماه محاسبه می‌شود: **{period}** · واحد خدمت: **{service_meta['unit']}**"
    )
    if record_type == RECORD_TYPES[2]:
        st.info(
            "در نوع «عملکرد دوره مشابه سال قبل»، سال واردشده باید سال واقعیِ دادهٔ مقایسه‌ای باشد؛ مثلاً برای مقایسهٔ گزارش ۱۴۰۳، دادهٔ سال ۱۴۰۲ را وارد کنید."
        )

    existing = fetch_record_by_identity(year, month, section, service_name, record_type)
    if existing:
        sample_suffix = (
            " (نمونهٔ ساختگی؛ با ذخیره‌کردن به دادهٔ معمولی تبدیل می‌شود)"
            if existing["is_demo"]
            else ""
        )
        st.warning(
            "برای این سال/ماه/بخش/خدمت/نوع رکورد اطلاعاتی وجود دارد. ذخیره‌کردن مقادیر تازه، همان ردیف را به‌روزرسانی می‌کند."
            + sample_suffix
        )

    form_key = f"record_form_{service_meta['id']}_{year}_{month}_{record_type}"
    quantity_label = (
        "مقدار بودجهٔ عملیاتی" if record_type == RECORD_TYPES[1] else "مقدار عملیاتی"
    )
    with st.form(form_key):
        col1, col2, col3 = st.columns(3)
        with col1:
            quantity = st.number_input(
                quantity_label,
                min_value=0.0,
                value=float(existing["quantity"]) if existing else 0.0,
                step=1.0,
                format="%.2f",
                key=f"{form_key}_quantity",
            )
        with col2:
            revenue = st.number_input(
                "درآمد (میلیون ریال)",
                min_value=0.0,
                value=float(existing["revenue_million_rial"]) if existing else 0.0,
                step=100.0,
                format="%.2f",
                key=f"{form_key}_revenue",
            )
        with col3:
            cost = st.number_input(
                "هزینه (میلیون ریال)",
                min_value=0.0,
                value=float(existing["cost_million_rial"]) if existing else 0.0,
                step=100.0,
                format="%.2f",
                key=f"{form_key}_cost",
            )
        cost_checked = st.checkbox(
            "هزینه را بررسی کرده‌ام؛ صفر فقط در صورت واقعاً صفر بودن ثبت شود.",
            key=f"{form_key}_cost_checked",
        )
        submitted = st.form_submit_button(
            "ذخیرهٔ رکورد", type="primary", width="stretch"
        )

    st.caption(
        "واحد درآمد و هزینه میلیون ریال است. هزینهٔ نامشخص را صفر نزنید؛ ابتدا مبلغ را بررسی کنید."
    )
    if submitted:
        if not cost_checked:
            st.error("پیش از ذخیره، تأیید کنید که مبلغ هزینه بررسی شده است.")
            return
        try:
            record_id, action = save_record(
                year=year,
                month=month,
                section=section,
                service=service_name,
                record_type=record_type,
                quantity=quantity,
                revenue_million_rial=revenue,
                cost_million_rial=cost,
                actor=user["username"],
            )
            verb = "به‌روزرسانی شد" if action == "updated" else "ثبت شد"
            st.success(f"رکورد شمارهٔ {record_id} {verb}.")
        except (ValueError, sqlite3.IntegrityError) as exc:
            st.error(f"ثبت انجام نشد: {exc}")


def _records_tab(user: dict[str, str]) -> None:
    st.subheader("جست‌وجوی رکوردها")
    all_records = fetch_records()
    if not all_records:
        st.info("هنوز رکوردی ثبت نشده است.")
        return
    years = sorted({int(row["year"]) for row in all_records})
    col1, col2, col3 = st.columns(3)
    with col1:
        year_option = st.selectbox(
            "فیلتر سال", ["همهٔ سال‌ها", *years], key="records_year_filter"
        )
    with col2:
        section_option = st.selectbox(
            "فیلتر بخش", ["همهٔ بخش‌ها", *SECTIONS], key="records_section_filter"
        )
    with col3:
        type_option = st.selectbox(
            "فیلتر نوع رکورد", ["همهٔ انواع", *RECORD_TYPES], key="records_type_filter"
        )
    filtered = [
        row
        for row in all_records
        if (year_option == "همهٔ سال‌ها" or int(row["year"]) == int(year_option))
        and (section_option == "همهٔ بخش‌ها" or row["section"] == section_option)
        and (type_option == "همهٔ انواع" or row["record_type"] == type_option)
    ]
    if not filtered:
        st.info("رکوردی با این فیلترها پیدا نشد.")
        return
    df = pd.DataFrame(filtered)
    df["is_demo"] = df["is_demo"].map({1: "بله — نمونه", 0: "خیر"})
    display_cols = [column for column in RECORD_DISPLAY if column in df.columns]
    display = df[display_cols].rename(columns=RECORD_DISPLAY)
    st.dataframe(display, width="stretch", hide_index=True, height=500)
    download_table_buttons(display, "رکوردهای_داشبورد", "records_export")

    if user["role"] == "admin":
        st.divider()
        st.subheader("حذف دادهٔ نمونه یا یک رکورد")
        sample_count = demo_record_count()
        if sample_count:
            with st.form("delete_demo_form"):
                st.warning(
                    f"{sample_count:,} ردیف نمونهٔ ساختگی در پایگاه داده باقی مانده است."
                )
                confirm_demo = st.checkbox(
                    "حذف دائمی تمام ردیف‌های نمونه را تأیید می‌کنم.",
                    key="confirm_delete_demo",
                )
                delete_demo = st.form_submit_button(
                    "حذف داده‌های نمونه", type="secondary"
                )
            if delete_demo:
                if not confirm_demo:
                    st.error("برای ادامه، تأیید حذف را فعال کنید.")
                else:
                    deleted = delete_demo_records(user["username"])
                    st.success(f"{deleted:,} ردیف نمونه حذف شد.")
        if filtered:
            record_map = {int(row["id"]): row for row in filtered}
            record_ids = list(record_map)
            with st.form("delete_single_record_form"):
                selected_id = st.selectbox(
                    "رکورد موردنظر",
                    record_ids,
                    format_func=lambda record_id: _record_option_label(
                        record_map[record_id]
                    ),
                    key="delete_record_id",
                )
                confirm_record = st.checkbox(
                    "حذف این رکورد را تأیید می‌کنم.", key="confirm_delete_record"
                )
                delete_one = st.form_submit_button("حذف رکورد انتخاب‌شده")
            if delete_one:
                if not confirm_record:
                    st.error("برای ادامه، تأیید حذف را فعال کنید.")
                elif delete_record(int(selected_id), user["username"]):
                    st.success("رکورد حذف شد.")
                else:
                    st.warning("این رکورد قبلاً حذف شده است.")


def _record_option_label(row: dict[str, Any]) -> str:
    return (
        f"#{row['id']} · {row['year']}/{row['month']:02d} · {row['section']} · "
        f"{row['service']} · {row['record_type']}"
    )


def _services_tab(user: dict[str, str]) -> None:
    st.subheader("فهرست خدمات")
    services = fetch_services(include_inactive=True)
    if services:
        service_df = pd.DataFrame(services).rename(
            columns={
                "section": "بخش",
                "name": "شرح خدمت",
                "unit": "واحد سنجش",
                "is_active": "وضعیت فعال (۱=بله)",
            }
        )
        visible_columns = [
            column
            for column in ("بخش", "شرح خدمت", "واحد سنجش", "وضعیت فعال (۱=بله)")
            if column in service_df
        ]
        st.dataframe(service_df[visible_columns], width="stretch", hide_index=True)
    else:
        st.info("فهرست خدمات هنوز خالی است.")

    if user["role"] != "admin":
        st.caption("فقط مدیر می‌تواند فهرست خدمات را تغییر دهد.")
        return

    with st.expander("افزودن خدمت", expanded=False):
        with st.form("add_service_form"):
            section = st.selectbox("بخش خدمت", SECTIONS, key="new_service_section")
            name = st.text_input("نام خدمت", key="new_service_name")
            unit = st.text_input(
                "واحد سنجش", placeholder="مثلاً تن، روز یا فقره", key="new_service_unit"
            )
            submitted = st.form_submit_button("افزودن خدمت")
        if submitted:
            try:
                add_service(section, name, unit, user["username"])
                st.success("خدمت اضافه شد.")
            except (ValueError, sqlite3.IntegrityError) as exc:
                st.error(f"افزودن خدمت انجام نشد: {exc}")

    if services:
        service_by_id = {int(item["id"]): item for item in services}
        selected_id = st.selectbox(
            "خدمت برای ویرایش",
            list(service_by_id),
            format_func=lambda service_id: (
                f"{service_by_id[service_id]['section']} · {service_by_id[service_id]['name']} ({service_by_id[service_id]['unit']})"
            ),
            key="edit_service_id",
        )
        selected = service_by_id[int(selected_id)]
        with st.form(f"edit_service_form_{selected_id}"):
            new_name = st.text_input(
                "نام خدمت",
                value=selected["name"],
                key=f"edit_service_name_{selected_id}",
            )
            new_unit = st.text_input(
                "واحد سنجش",
                value=selected["unit"],
                key=f"edit_service_unit_{selected_id}",
            )
            state_options = ["فعال", "غیرفعال"]
            current_state = "فعال" if selected["is_active"] else "غیرفعال"
            new_state = st.selectbox(
                "وضعیت خدمت",
                state_options,
                index=state_options.index(current_state),
                key=f"edit_service_state_{selected_id}",
            )
            submitted = st.form_submit_button("ذخیرهٔ تغییرات")
        if submitted:
            try:
                update_service(int(selected_id), new_name, new_unit, user["username"])
                set_service_active(
                    int(selected_id), new_state == "فعال", user["username"]
                )
                st.success("فهرست خدمت به‌روزرسانی شد.")
            except (ValueError, sqlite3.IntegrityError) as exc:
                st.error(f"به‌روزرسانی انجام نشد: {exc}")
