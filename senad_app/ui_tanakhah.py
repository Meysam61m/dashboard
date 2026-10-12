"""صفحه تنخواه: ثبت واریز، کارتکس و مانده شعب."""
import pandas as pd
import streamlit as st

from . import auth, config, db, services
from .ui import fmt_money


def page() -> None:
    user = st.session_state["user"]
    st.title("💰 تنخواه")

    branches = services.list_branches()
    allowed = auth.user_branch_ids(user["id"], user["role"])
    if allowed is not None:
        branches = [b for b in branches if b["id"] in allowed]
    if not branches:
        st.info("شعبه‌ای در دسترس نیست.")
        return

    labels = [f"{b['code']} — {b['name']}" for b in branches]
    sel = st.selectbox("شعبه", labels)
    branch = branches[labels.index(sel)]
    summary = services.tanakhah_summary(branch["id"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("آخرین واریز تنخواه", summary["last_date"] or "—")
    c2.metric("مجموع دریافتی‌ها (ریال)", fmt_money(summary["total_in"]))
    c3.metric("مجموع اسناد نهایی (ریال)", fmt_money(summary["total_docs"]))
    c4.metric("مانده تنخواه (ریال)", fmt_money(summary["balance"]))

    alert = float(db.get_setting("tanakhah_alert", "0") or 0)
    if alert and summary["balance"] < alert:
        st.warning(f"مانده تنخواه این شعبه کمتر از آستانه هشدار ({fmt_money(alert)} ریال) است.")

    st.divider()

    if config.can(user["role"], "tanakhah"):
        with st.form("tanakhah_form", clear_on_submit=True):
            st.subheader("ثبت واریز تنخواه")
            c1, c2, c3, c4 = st.columns([1.5, 1.5, 3, 1])
            tx_date = c1.text_input("تاریخ واریز", value=services.today_jalali())
            amount = c2.number_input("مبلغ (ریال)", min_value=0.0, step=1_000_000.0, format="%.0f")
            desc = c3.text_input("بابت / شرح")
            if c4.form_submit_button("💾 ثبت", type="primary"):
                try:
                    tx_id = services.add_tanakhah(user["id"], branch["id"], tx_date, amount, desc)
                    services.audit(user, "add_tanakhah", "tanakhah_tx", tx_id,
                                   f"شعبه={sel}، مبلغ={fmt_money(amount)}، تاریخ={tx_date}")
                    st.success("واریز تنخواه ثبت شد.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    else:
        st.caption("شما فقط مجوز مشاهده تنخواه را دارید.")

    st.subheader("کارتکس تنخواه")
    txs = [t for t in services.list_tanakhah(branch["id"])]
    if txs:
        df = pd.DataFrame([{
            "تاریخ": t["tx_date"], "مبلغ (ریال)": fmt_money(t["amount"]),
            "شرح": t["description"], "ثبت‌کننده": t["creator_name"],
        } for t in txs])
        st.dataframe(df, hide_index=True, use_container_width=True)
        if config.can(user["role"], "tanakhah"):
            ids = [t["id"] for t in txs]
            pick = st.selectbox("حذف واریز (فقط مدیر/سرپرست — با ثبت در لاگ)",
                                options=ids,
                                format_func=lambda i: next(
                                    f"{t['tx_date']} — {fmt_money(t['amount'])} — {t['description'][:30]}"
                                    for t in txs if t["id"] == i))
            if st.button("حذف واریز انتخاب‌شده"):
                services.delete_tanakhah(pick)
                services.audit(user, "delete_tanakhah", "tanakhah_tx", pick, f"شعبه={sel}")
                st.warning("واریز حذف شد.")
                st.rerun()
    else:
        st.info("هنوز واریزی ثبت نشده است.")
