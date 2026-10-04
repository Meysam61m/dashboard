from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from dashboard_app.auth import (
    change_own_password,
    create_user,
    list_users,
    reset_user_password,
    set_user_active,
)
from dashboard_app.config import ROLE_LABELS
from dashboard_app.database import db_connection, write_audit
from dashboard_app.repository import database_backup_bytes, fetch_audit_logs
from dashboard_app.views.common import page_heading


def render_user_admin(actor: dict[str, str]) -> None:
    page_heading(
        "مدیریت کاربران",
        "ساخت حساب محلی، تعیین سطح دسترسی، غیرفعال‌سازی و بازنشانی گذرواژه.",
    )
    st.caption("حداکثر ۱۰ حساب فعال برای این نسخه؛ نقش‌ها: مدیر، ثبت‌کننده و فقط‌خواندنی.")
    if actor["role"] != "admin":
        st.error("این بخش فقط در دسترس مدیر است.")
        return

    with st.expander("ساخت حساب کاربری", expanded=True):
        with st.form("create_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                username = st.text_input("نام کاربری (لاتین)", key="new_user_username")
                display_name = st.text_input("نام نمایشی", key="new_user_display_name")
            with col2:
                role = st.selectbox(
                    "نقش",
                    list(ROLE_LABELS),
                    format_func=lambda value: ROLE_LABELS[value],
                    key="new_user_role",
                )
                password = st.text_input(
                    "گذرواژهٔ موقت (حداقل ۱۲ نویسه)",
                    type="password",
                    key="new_user_password",
                )
                confirm_password = st.text_input(
                    "تکرار گذرواژه", type="password", key="new_user_confirm_password"
                )
            submitted = st.form_submit_button("ایجاد حساب", type="primary")
        if submitted:
            if password != confirm_password:
                st.error("گذرواژه و تکرار آن یکسان نیستند.")
            else:
                try:
                    create_user(
                        username, display_name, password, role, actor["username"]
                    )
                    st.success(
                        "حساب ساخته شد. گذرواژه را از مسیر امن به کاربر تحویل دهید."
                    )
                except (ValueError, sqlite3.IntegrityError) as exc:
                    st.error(f"ساخت حساب انجام نشد: {exc}")

    users = list_users()
    if users:
        table = pd.DataFrame(users)
        table["role"] = table["role"].map(ROLE_LABELS)
        table["is_active"] = table["is_active"].map({1: "فعال", 0: "غیرفعال"})
        table = table.rename(
            columns={
                "username": "نام کاربری",
                "display_name": "نام نمایشی",
                "role": "نقش",
                "is_active": "وضعیت",
                "created_by": "ایجادکننده",
                "created_at": "زمان ایجاد (UTC)",
                "updated_at": "آخرین به‌روزرسانی (UTC)",
                "failed_attempts": "تلاش ناموفق اخیر",
                "locked_until": "قفل تا (UTC)",
            }
        )
        visible = [
            column
            for column in (
                "نام کاربری",
                "نام نمایشی",
                "نقش",
                "وضعیت",
                "ایجادکننده",
                "زمان ایجاد (UTC)",
                "آخرین به‌روزرسانی (UTC)",
                "تلاش ناموفق اخیر",
                "قفل تا (UTC)",
            )
            if column in table
        ]
        st.subheader("حساب‌های موجود")
        st.dataframe(table[visible], width="stretch", hide_index=True)

        options = [
            row["username"] for row in users if row["username"] != actor["username"]
        ]
        if options:
            user_by_name = {row["username"]: row for row in users}
            selected = st.selectbox(
                "کاربر برای مدیریت",
                options,
                format_func=lambda username: (
                    f"{user_by_name[username]['display_name']} ({username})"
                ),
                key="manage_user_selection",
            )
            selected_user = user_by_name[selected]
            with st.form(f"toggle_user_form_{selected}"):
                statuses = ["فعال", "غیرفعال"]
                current_status = "فعال" if selected_user["is_active"] else "غیرفعال"
                status = st.selectbox(
                    "وضعیت دسترسی",
                    statuses,
                    index=statuses.index(current_status),
                    key=f"user_status_{selected}",
                )
                submitted = st.form_submit_button("ذخیرهٔ وضعیت")
            if submitted:
                try:
                    set_user_active(selected, status == "فعال", actor["username"])
                    st.success("وضعیت کاربر ذخیره شد.")
                except ValueError as exc:
                    st.error(str(exc))

            with st.expander("بازنشانی گذرواژهٔ کاربر"):
                with st.form(f"reset_password_form_{selected}"):
                    new_password = st.text_input(
                        "گذرواژهٔ تازه (حداقل ۱۲ نویسه)",
                        type="password",
                        key=f"reset_pw_{selected}",
                    )
                    confirm = st.text_input(
                        "تکرار گذرواژهٔ تازه",
                        type="password",
                        key=f"reset_confirm_{selected}",
                    )
                    reset = st.form_submit_button("بازنشانی گذرواژه")
                if reset:
                    if new_password != confirm:
                        st.error("گذرواژه و تکرار آن یکسان نیستند.")
                    else:
                        try:
                            reset_user_password(
                                selected, new_password, actor["username"]
                            )
                            st.success("گذرواژه بازنشانی شد.")
                        except ValueError as exc:
                            st.error(str(exc))
        else:
            st.info("برای مدیریت حساب‌های دیگر، ابتدا یک کاربر تازه بسازید.")


def render_security_page(user: dict[str, str]) -> None:
    page_heading(
        "حساب و امنیت",
        "گذرواژهٔ حساب خود را تغییر دهید یا ابزارهای مدیریتی محلی را باز کنید.",
    )
    with st.expander("تغییر گذرواژهٔ من", expanded=True):
        with st.form("change_own_password_form"):
            current = st.text_input(
                "گذرواژهٔ فعلی", type="password", key="own_current_password"
            )
            new = st.text_input(
                "گذرواژهٔ تازه (حداقل ۱۲ نویسه)", type="password", key="own_new_password"
            )
            confirm = st.text_input(
                "تکرار گذرواژهٔ تازه", type="password", key="own_confirm_password"
            )
            submitted = st.form_submit_button("تغییر گذرواژه")
        if submitted:
            if new != confirm:
                st.error("گذرواژهٔ تازه و تکرار آن یکسان نیستند.")
            else:
                try:
                    change_own_password(user["username"], current, new)
                    st.success("گذرواژه تغییر کرد.")
                except ValueError as exc:
                    st.error(str(exc))

    if user["role"] != "admin":
        return

    st.divider()
    st.subheader("پشتیبان‌گیری محلی")
    st.warning(
        "فایل پشتیبان شامل داده‌های مالی و اطلاعات هش‌شدهٔ حساب‌هاست؛ آن را در محل امن و محدود نگه دارید."
    )
    try:
        backup = database_backup_bytes()
        downloaded = st.download_button(
            "دریافت نسخهٔ پشتیبان SQLite",
            data=backup,
            file_name=f"finance_dashboard_backup_{datetime.now(timezone.utc).date().isoformat()}.sqlite3",
            mime="application/vnd.sqlite3",
            key="sqlite_backup_download",
        )
        if downloaded:
            with db_connection() as connection:
                write_audit(
                    connection,
                    user["username"],
                    "download_backup",
                    "database",
                    details={"bytes": len(backup)},
                )
                connection.commit()
    except (sqlite3.Error, OSError) as exc:
        st.error(f"تهیهٔ پشتیبان انجام نشد: {exc}")

    st.divider()
    st.subheader("سابقهٔ تغییرات")
    logs = fetch_audit_logs(300)
    if not logs:
        st.info("هنوز رویدادی ثبت نشده است.")
    else:
        audit = pd.DataFrame(logs).rename(
            columns={
                "id": "شناسه",
                "actor": "کاربر",
                "action": "رویداد",
                "entity": "موضوع",
                "entity_id": "شناسهٔ موضوع",
                "details": "جزئیات",
                "created_at": "زمان (UTC)",
            }
        )
        st.dataframe(audit, width="stretch", hide_index=True, height=420)
