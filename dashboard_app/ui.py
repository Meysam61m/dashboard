from __future__ import annotations

import csv
import sqlite3
import time

import streamlit as st

from dashboard_app.auth import (
    authenticate,
    create_initial_admin,
    get_active_user,
    user_count,
)
from dashboard_app.config import APP_SUBTITLE, APP_TITLE, ROLE_LABELS
from dashboard_app.database import db_connection, initialize_db, utc_now, write_audit
from dashboard_app.seed import seed_demo_data
from dashboard_app.views.admin import render_security_page, render_user_admin
from dashboard_app.views.analytics import render_dashboard, render_final_report
from dashboard_app.views.common import apply_styles
from dashboard_app.views.data import render_data_management

SESSION_TIMEOUT_SECONDS = 30 * 60


def run_app() -> None:
    try:
        initialize_db()
        seed_demo_data()
    except (sqlite3.Error, OSError, ValueError, KeyError, csv.Error) as exc:
        st.error(
            "راه‌اندازی پایگاه داده انجام نشد. مسیر ذخیره‌سازی و مجوز نوشتن را بررسی کنید."
        )
        st.exception(exc)
        return

    apply_styles()
    st.markdown(
        f'<div class="app-kicker">نسخهٔ محلی · بدون اتصال ابری</div><div class="app-title">{APP_TITLE}</div>',
        unsafe_allow_html=True,
    )

    if user_count() == 0:
        _render_first_admin_setup()
        return

    user = st.session_state.get("auth_user")
    if not user:
        _render_login()
        return

    now = time.time()
    if now - float(user.get("last_activity", now)) > SESSION_TIMEOUT_SECONDS:
        _write_logout_audit(user["username"], "session_timeout")
        st.session_state.pop("auth_user", None)
        st.warning("نشست شما به‌دلیل عدم فعالیت پایان یافت؛ دوباره وارد شوید.")
        _render_login()
        return
    active_user = get_active_user(user["username"])
    if active_user is None:
        _write_logout_audit(user["username"], "account_disabled")
        st.session_state.pop("auth_user", None)
        st.warning("دسترسی این حساب غیرفعال شده است؛ با مدیر تماس بگیرید.")
        _render_login()
        return
    user.update(active_user)
    user["last_activity"] = now
    st.session_state["auth_user"] = user

    _render_navigation(user)


def _render_first_admin_setup() -> None:
    st.subheader("راه‌اندازی اولیهٔ مدیر")
    st.info(
        "پیش از در دسترس قراردادن برنامه برای شبکه، حساب مدیر را روی رایانهٔ میزبان بسازید."
    )
    st.markdown("برای امنیت، نام کاربری لاتین و گذرواژهٔ حداقل ۱۲ نویسه انتخاب کنید.")
    with st.form("first_admin_setup_form"):
        username = st.text_input("نام کاربری مدیر", key="bootstrap_username")
        display_name = st.text_input("نام نمایشی", key="bootstrap_display_name")
        password = st.text_input("گذرواژه", type="password", key="bootstrap_password")
        confirm = st.text_input(
            "تکرار گذرواژه", type="password", key="bootstrap_confirm"
        )
        submitted = st.form_submit_button("ساخت حساب مدیر", type="primary")
    if submitted:
        if password != confirm:
            st.error("گذرواژه و تکرار آن یکسان نیستند.")
        else:
            try:
                create_initial_admin(username, display_name, password)
                st.success("حساب مدیر ساخته شد. اکنون وارد شوید.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except sqlite3.Error as exc:
                st.error(f"ساخت حساب انجام نشد: {exc}")


def _render_login() -> None:
    st.subheader("ورود به سامانه")
    col1, col2 = st.columns([1.15, 1])
    with col1:
        st.markdown(f"### ورود کاربران مجاز\n{APP_SUBTITLE}")
        st.caption("حساب‌ها و داده‌ها روی همین سرور محلی نگهداری می‌شوند.")
    with col2:
        with st.form("login_form"):
            username = st.text_input("نام کاربری", key="login_username")
            password = st.text_input("گذرواژه", type="password", key="login_password")
            submitted = st.form_submit_button("ورود", type="primary", width="stretch")
        if submitted:
            try:
                user = authenticate(username, password)
            except sqlite3.Error:
                user = None
            if user:
                st.session_state["auth_user"] = {**user, "last_activity": time.time()}
                st.rerun()
            else:
                st.error(
                    "ورود انجام نشد. اطلاعات را بررسی کنید یا در صورت قفل‌شدن حساب با مدیر تماس بگیرید."
                )


def _write_logout_audit(username: str, reason: str = "user_logout") -> None:
    try:
        with db_connection() as connection:
            write_audit(
                connection,
                username,
                "logout",
                "auth",
                details={"reason": reason, "at": utc_now()},
            )
            connection.commit()
    except sqlite3.Error:
        # A logout should still succeed even if the audit database is temporarily busy.
        return


def _render_navigation(user: dict[str, str]) -> None:
    role = user.get("role", "viewer")
    pages = ["داشبورد", "گزارش نهایی"]
    if role in ("admin", "editor"):
        pages.append("ثبت و مدیریت داده‌ها")
    pages.append("حساب و امنیت")
    if role == "admin":
        pages.append("مدیریت کاربران")

    with st.sidebar:
        st.markdown("### مرکز کنترل")
        st.write(f"**{user.get('display_name', user['username'])}**")
        st.caption(f"نقش: {ROLE_LABELS.get(role, role)}")
        page = st.radio("بخش", pages, key="main_navigation")
        st.divider()
        st.caption("On-Premise · SQLite محلی · دسترسی شبکهٔ داخلی")
        if st.button("خروج", width="stretch", key="logout_button"):
            _write_logout_audit(user["username"])
            st.session_state.pop("auth_user", None)
            st.rerun()

    if page == "داشبورد":
        render_dashboard()
    elif page == "گزارش نهایی":
        render_final_report()
    elif page == "ثبت و مدیریت داده‌ها":
        render_data_management(user)
    elif page == "حساب و امنیت":
        render_security_page(user)
    elif page == "مدیریت کاربران":
        render_user_admin(user)
