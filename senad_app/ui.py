"""رابط کاربری اصلی: ورود، منو، داشبورد."""
import pandas as pd
import streamlit as st

from . import auth, config, db, services


def inject_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700&display=swap');
        html, body, [class*="css"], .stApp { font-family: Vazirmatn, Tahoma, Arial, sans-serif !important; }
        .block-container { direction: rtl; }
        h1, h2, h3, h4, p, label, .stMarkdown { direction: rtl; text-align: right; }
        div[data-testid="stSidebar"] { direction: rtl; }
        .senad-metric { border: 1px solid #d0d7de; border-radius: 10px; padding: 12px 16px; text-align: center; }
        .senad-metric b { font-size: 22px; display: block; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def fmt_money(v) -> str:
    try:
        return f"{float(v or 0):,.0f}"
    except (TypeError, ValueError):
        return "—"


def sidebar() -> str:
    user = st.session_state["user"]
    st.sidebar.markdown(f"### 👤 {user['full_name'] or user['username']}")
    st.sidebar.caption(f"نقش: {config.ROLES.get(user['role'], user['role'])}")
    st.sidebar.divider()

    options = {"📊 داشبورد": "dashboard", "📄 اسناد": "documents"}
    if config.can(user["role"], "tanakhah") or user["role"] in ("karperdaz", "viewer"):
        options["💰 تنخواه"] = "tanakhah"
    if config.can(user["role"], "manage_users") or config.can(user["role"], "view_log"):
        options["⚙️ مدیریت"] = "admin"

    labels = list(options.keys())
    default = st.session_state.get("page_label", labels[0])
    if default not in labels:
        default = labels[0]
    choice = st.sidebar.radio("منو", labels, index=labels.index(default), label_visibility="collapsed",
                              key="menu_radio")
    st.session_state["page_label"] = choice
    st.sidebar.divider()
    if st.sidebar.button("خروج از حساب"):
        for k in ("user", "page_label", "view_doc", "edit_doc"):
            st.session_state.pop(k, None)
        st.rerun()
    return options[choice]


def login_gate() -> bool:
    if "user" in st.session_state:
        return True

    st.title("🧾 سیستم ثبت و چاپ سند کارپردازی")
    if not auth.has_users():
        st.info("به برنامه خوش آمدید. برای شروع، حساب مدیر سیستم را بسازید.")
        with st.form("setup"):
            username = st.text_input("نام کاربری")
            full_name = st.text_input("نام کامل")
            pw = st.text_input("گذرواژه", type="password")
            pw2 = st.text_input("تکرار گذرواژه", type="password")
            if st.form_submit_button("ساخت حساب مدیر", type="primary"):
                if not username.strip() or len(pw) < 6:
                    st.error("نام کاربری الزامی و گذرواژه باید حداقل ۶ کاراکتر باشد.")
                elif pw != pw2:
                    st.error("گذرواژه‌ها یکسان نیستند.")
                else:
                    try:
                        uid = auth.create_user(username, pw, full_name, "admin")
                        user = auth.authenticate(username.strip(), pw)
                        st.session_state["user"] = user
                        services.audit(user, "create_admin", "users", uid, "ساخت حساب مدیر (راه‌اندازی اولیه)")
                        st.rerun()
                    except Exception as e:
                        st.error(f"خطا: {e}")
        return False

    with st.form("login"):
        st.subheader("ورود")
        username = st.text_input("نام کاربری")
        pw = st.text_input("گذرواژه", type="password")
        if st.form_submit_button("ورود", type="primary"):
            user = auth.authenticate(username, pw)
            if user:
                st.session_state["user"] = user
                services.audit(user, "login", details="ورود موفق")
                st.rerun()
            else:
                st.error("نام کاربری یا گذرواژه نادرست است.")
    return False


def dashboard_page() -> None:
    user = st.session_state["user"]
    st.title("📊 داشبورد")
    branch_ids = auth.user_branch_ids(user["id"], user["role"])
    stats = services.dashboard_stats(branch_ids)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("اسناد امروز", stats["today_count"])
    c2.metric("اسناد این ماه", stats["month_count"])
    c3.metric("جمع کل اسناد این ماه (ریال)", fmt_money(stats["month_total"]))
    c4.metric("پیش‌نویس‌های باز", stats["draft_count"])

    st.divider()
    st.subheader("مانده تنخواه شعب")
    branches = services.list_branches()
    if branch_ids is not None:
        branches = [b for b in branches if b["id"] in branch_ids]
    if not branches:
        st.info("شعبه‌ای تعریف نشده است. از منوی مدیریت، شعبه اضافه کنید.")
        return
    rows = []
    for b in branches:
        s = services.tanakhah_summary(b["id"])
        rows.append({
            "کد": b["code"], "شعبه": b["name"],
            "آخرین واریز تنخواه": s["last_date"] or "—",
            "مجموع دریافتی": fmt_money(s["total_in"]),
            "مجموع اسناد": fmt_money(s["total_docs"]),
            "مانده تنخواه": fmt_money(s["balance"]),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def run() -> None:
    # توجه: st.set_page_config در app.py صدا زده می‌شود (باید اولین دستور استریملیت باشد)
    db.init_db()
    inject_css()
    services.auto_backup_if_due()

    if not login_gate():
        return

    page = sidebar()
    if page == "dashboard":
        dashboard_page()
    elif page == "documents":
        from . import ui_documents
        ui_documents.page()
    elif page == "tanakhah":
        from . import ui_tanakhah
        ui_tanakhah.page()
    elif page == "admin":
        from . import ui_admin
        ui_admin.page()
