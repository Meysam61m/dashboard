"""بخش مدیریت: کاربران، شعب، تنظیمات چاپ، بکاپ و لاگ."""
import base64

import pandas as pd
import streamlit as st

from . import auth, config, db, services
from .ui import fmt_money


def page() -> None:
    user = st.session_state["user"]
    st.title("⚙️ مدیریت")

    tabs = []
    if config.can(user["role"], "manage_users"):
        tabs += ["👥 کاربران", "🏢 شعب"]
    if config.can(user["role"], "manage_settings"):
        tabs += ["🖨 تنظیمات چاپ"]
    if config.can(user["role"], "backup"):
        tabs += ["💾 بکاپ"]
    if config.can(user["role"], "view_log"):
        tabs += ["📜 لاگ تغییرات"]

    views = st.tabs(tabs)
    idx = {name: i for i, name in enumerate(tabs)}

    if "👥 کاربران" in idx:
        with views[idx["👥 کاربران"]]:
            _users_tab()
    if "🏢 شعب" in idx:
        with views[idx["🏢 شعب"]]:
            _branches_tab()
    if "🖨 تنظیمات چاپ" in idx:
        with views[idx["🖨 تنظیمات چاپ"]]:
            _settings_tab()
    if "💾 بکاپ" in idx:
        with views[idx["💾 بکاپ"]]:
            _backup_tab()
    if "📜 لاگ تغییرات" in idx:
        with views[idx["📜 لاگ تغییرات"]]:
            _log_tab()


def _users_tab() -> None:
    st.subheader("تعریف کاربر و سطح دسترسی")
    branches = services.list_branches()
    with st.expander("➕ کاربر جدید", expanded=False):
        with st.form("new_user"):
            c1, c2, c3, c4 = st.columns(4)
            username = c1.text_input("نام کاربری")
            full_name = c2.text_input("نام کامل")
            role = c3.selectbox("نقش", list(config.ROLES.keys()), format_func=lambda r: config.ROLES[r])
            pw = c4.text_input("گذرواژه", type="password")
            branch_sel = st.multiselect("شعبه‌های قابل دسترسی",
                                        options=[b["id"] for b in branches],
                                        format_func=lambda i: next(
                                            f"{b['code']} — {b['name']}" for b in branches if b["id"] == i))
            if st.form_submit_button("ساخت کاربر", type="primary"):
                if not username.strip() or len(pw) < 6:
                    st.error("نام کاربری الزامی و گذرواژه حداقل ۶ کاراکتر باشد.")
                else:
                    try:
                        uid = auth.create_user(username, pw, full_name, role)
                        auth.set_user_branches(uid, branch_sel)
                        services.audit(st.session_state["user"], "create_user", "users", uid,
                                       f"{username} ({config.ROLES[role]})")
                        st.success("کاربر ساخته شد.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"خطا: {e}")

    for u in auth.list_users():
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 3])
            c1.markdown(f"**{u['username']}**")
            c2.write(u["full_name"])
            c3.write(config.ROLES.get(u["role"], u["role"]))
            c4.write("فعال" if u["is_active"] else "غیرفعال")
            c5.caption("شعبه‌ها: " + (", ".join(f"{b['code']}—{b['name']}" for b in u["branches"]) or "—"))
            with st.expander(f"ویرایش {u['username']}"):
                with st.form(f"edit_u{u['id']}"):
                    e1, e2, e3 = st.columns(3)
                    full_name = e1.text_input("نام کامل", value=u["full_name"])
                    role = e2.selectbox("نقش", list(config.ROLES.keys()),
                                        index=list(config.ROLES.keys()).index(u["role"]),
                                        format_func=lambda r: config.ROLES[r])
                    is_active = e3.selectbox("وضعیت", [1, 0], index=0 if u["is_active"] else 1,
                                             format_func=lambda v: "فعال" if v else "غیرفعال")
                    branch_sel = st.multiselect("شعبه‌ها", options=[b["id"] for b in branches],
                                                default=[b["id"] for b in u["branches"]],
                                                format_func=lambda i: next(
                                                    f"{b['code']} — {b['name']}" for b in branches if b["id"] == i))
                    new_pw = st.text_input("گذرواژه جدید (برای تغییر)", type="password")
                    if st.form_submit_button("ذخیره"):
                        auth.update_user(u["id"], full_name, role, is_active)
                        auth.set_user_branches(u["id"], branch_sel)
                        if new_pw:
                            if len(new_pw) < 6:
                                st.error("گذرواژه جدید حداقل ۶ کاراکتر باشد.")
                            else:
                                auth.reset_password(u["id"], new_pw)
                        services.audit(st.session_state["user"], "update_user", "users", u["id"], u["username"])
                        st.success("به‌روزرسانی شد.")
                        st.rerun()


def _branches_tab() -> None:
    st.subheader("تعریف شعب")
    with st.form("new_branch", clear_on_submit=True):
        c1, c2, c3 = st.columns([1, 3, 1])
        code = c1.text_input("کد شعبه (دو رقمی)", placeholder="45")
        name = c2.text_input("نام شعبه")
        if c3.form_submit_button("افزودن شعبه", type="primary"):
            try:
                services.add_branch(code, name)
                services.audit(st.session_state["user"], "add_branch", "branches", code, name)
                st.success("شعبه اضافه شد.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    for b in services.list_branches():
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1, 3, 1.5, 2])
            code = c1.text_input("کد", value=b["code"], key=f"bc{b['id']}")
            name = c2.text_input("نام", value=b["name"], key=f"bn{b['id']}")
            active = c3.selectbox("وضعیت", [1, 0], index=0 if b["is_active"] else 1, key=f"ba{b['id']}",
                                  format_func=lambda v: "فعال" if v else "غیرفعال")
            if c4.button("ذخیره", key=f"bs{b['id']}"):
                try:
                    services.update_branch(b["id"], code, name, active)
                    services.audit(st.session_state["user"], "update_branch", "branches", b["id"], f"{code} {name}")
                    st.success("ذخیره شد.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


def _settings_tab() -> None:
    st.subheader("تنظیمات صفحه چاپ و لوگو")
    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("**لوگوی سند چاپی**")
        if config.LOGO_PATH.exists():
            st.image(str(config.LOGO_PATH), width=180)
        uploaded = st.file_uploader("انتخاب لوگو (PNG/JPG)", type=["png", "jpg", "jpeg"])
        if uploaded and st.button("ذخیره لوگو"):
            config.LOGO_PATH.write_bytes(uploaded.getbuffer())
            services.audit(st.session_state["user"], "update_logo", "settings")
            st.success("لوگو ذخیره شد.")
            st.rerun()

    with col2:
        with st.form("settings_form"):
            s = {}
            for key in ("company_name", "complex_name", "national_id", "economic_code",
                        "doc_title", "doc_control", "doc_control_date"):
                s[key] = st.text_input(key, value=db.get_setting(key, config.DEFAULT_SETTINGS.get(key, "")))
            s["standard_text"] = st.text_area("متن استاندارد زیر جدول",
                                             value=db.get_setting("standard_text", config.DEFAULT_SETTINGS["standard_text"]))
            c1, c2, c3 = st.columns(3)
            s["number_separator"] = c1.text_input("جداکننده شماره سند",
                                                  value=db.get_setting("number_separator", "-"))
            s["seq_width"] = c2.text_input("تعداد رقم عدد ترتیبی",
                                           value=db.get_setting("seq_width", "4"))
            s["tanakhah_alert"] = c3.text_input("آستانه هشدار مانده تنخواه (ریال)",
                                                value=db.get_setting("tanakhah_alert", "200000000"))
            if st.form_submit_button("ذخیره تنظیمات", type="primary"):
                for k, v in s.items():
                    db.set_setting(k, v)
                services.audit(st.session_state["user"], "update_settings", "settings", details=str(list(s)))
                st.success("تنظیمات ذخیره شد.")
                st.rerun()


def _backup_tab() -> None:
    st.subheader("پشتیبان‌گیری")
    st.caption(f"پشتیبان خودکار: هر روز یک‌بار هنگام ورود به برنامه (در {config.BACKUP_DIR})")
    if st.button("📥 دریافت پشتیبان دستی", type="primary"):
        path = services.backup_now("manual")
        services.audit(st.session_state["user"], "backup", "backups", path.name)
        with open(path, "rb") as f:
            st.download_button("دانلود فایل پشتیبان", data=f.read(), file_name=path.name)
        st.success(f"پشتیبان ساخته شد: {path.name}")

    rows = services.list_backups()
    if rows:
        df = pd.DataFrame([{
            "نام فایل": r["name"], "حجم (بایت)": f"{r['size']:,}",
        } for r in rows])
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.info("هنوز پشتیبانی ساخته نشده است.")


def _log_tab() -> None:
    st.subheader("📜 سابقه تغییرات")
    rows = services.list_log()
    if not rows:
        st.info("لاگی ثبت نشده است.")
        return
    df = pd.DataFrame([{
        "زمان": r["created_at"], "کاربر": r["username"], "عملیات": r["action"],
        "موجودیت": r["entity"], "شناسه": r["entity_id"], "جزئیات": r["details"],
    } for r in rows])
    st.dataframe(df, hide_index=True, use_container_width=True)
