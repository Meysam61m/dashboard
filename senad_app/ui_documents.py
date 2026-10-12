"""صفحه اسناد: فهرست، ثبت/ویرایش پیش‌نویس، نهایی‌کردن، ابطال و چاپ."""
import html as html_mod

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from . import auth, config, db, printing, services
from .ui import fmt_money

STATUS_LABEL = {"": "همه وضعیت‌ها", "draft": "پیش‌نویس", "final": "نهایی", "void": "باطل‌شده"}


def _branch_options() -> list[dict]:
    user = st.session_state["user"]
    branches = services.list_branches()
    allowed = auth.user_branch_ids(user["id"], user["role"])
    if allowed is not None:
        branches = [b for b in branches if b["id"] in allowed]
    return branches


def _can_edit(doc: dict) -> bool:
    user = st.session_state["user"]
    if doc["status"] == "void":
        return False
    if doc["status"] == "draft":
        return config.can(user["role"], "edit_draft") and (
            user["role"] != "karperdaz" or doc["created_by"] == user["id"]
        )
    return config.can(user["role"], "edit_final")


def _can_finalize(doc: dict) -> bool:
    user = st.session_state["user"]
    return doc["status"] == "draft" and config.can(user["role"], "finalize") and (
        user["role"] != "karperdaz" or doc["created_by"] == user["id"]
    )


def page() -> None:
    user = st.session_state["user"]

    if st.session_state.get("print_doc"):
        _print_view(st.session_state["print_doc"])
        return
    if st.session_state.get("edit_doc") is not None:
        _editor(st.session_state["edit_doc"])
        return

    st.title("📄 اسناد")
    c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.2, 1.2, 2])
    branches = _branch_options()
    branch_names = ["همه شعب"] + [f"{b['code']} — {b['name']}" for b in branches]
    sel = c1.selectbox("شعبه", branch_names)
    status = c2.selectbox("وضعیت", list(STATUS_LABEL.values()))
    d_from = c3.text_input("از تاریخ", placeholder="1405/01/01")
    d_to = c4.text_input("تا تاریخ", placeholder="1405/12/29")
    search = c5.text_input("جست‌وجو", placeholder="شماره سند / شرح / عنوان")

    branch_ids = None
    if sel != "همه شعب":
        idx = branch_names.index(sel) - 1
        branch_ids = [branches[idx]["id"]]
    else:
        branch_ids = auth.user_branch_ids(user["id"], user["role"])

    status_val = [k for k, v in STATUS_LABEL.items() if v == status][0]
    created_by = user["id"] if user["role"] == "karperdaz" else None

    if config.can(user["role"], "create") and st.button("➕ سند جدید", type="primary"):
        st.session_state["edit_doc"] = 0
        st.rerun()

    docs = services.list_documents(
        branch_ids=branch_ids, status=status_val,
        date_from=d_from, date_to=d_to, search=search, created_by=created_by,
    )
    if not docs:
        st.info("سندی یافت نشد.")
        return

    for d in docs:
        with st.container(border=True):
            r1 = st.columns([3, 2, 2, 2, 2, 3, 3])
            r1[0].markdown(f"**{d['doc_number'] or 'بدون شماره (پیش‌نویس)'}**")
            r1[1].write(d["doc_date"])
            r1[2].write(f"{d['branch_code']} — {d['branch_name']}")
            r1[3].write(f"💰 {fmt_money(d['total'])}")
            r1[4].write(STATUS_LABEL[d["status"]])
            r1[5].caption(f"ثبت: {d['creator_name']} | چاپ: {d['print_count']}")
            b = r1[6].columns(2)
            if b[0].button("👁 مشاهده/چاپ", key=f"v{d['id']}"):
                st.session_state["print_doc"] = d["id"]
                st.rerun()
            if _can_edit(d) and b[1].button("✏️ ویرایش", key=f"e{d['id']}"):
                st.session_state["edit_doc"] = d["id"]
                st.rerun()


def _editor(doc_id: int) -> None:
    user = st.session_state["user"]
    branches = _branch_options()
    if not branches:
        st.error("شما به هیچ شعبه‌ای دسترسی ندارید.")
        if st.button("بازگشت"):
            st.session_state.pop("edit_doc")
            st.rerun()
        return

    doc = services.get_document(doc_id) if doc_id else None
    is_new = doc is None

    st.title("➕ سند جدید" if is_new else f"✏️ ویرایش سند {doc['doc_number'] or '(پیش‌نویس)'}")
    if doc and not _can_edit(doc):
        st.error("شما مجوز ویرایش این سند را ندارید.")
        if st.button("بازگشت"):
            st.session_state.pop("edit_doc")
            st.rerun()
        return

    with st.form("doc_form"):
        c1, c2, c3 = st.columns([2, 2, 3])
        branch_labels = [f"{b['code']} — {b['name']}" for b in branches]
        cur_idx = 0
        if doc:
            for i, b in enumerate(branches):
                if b["id"] == doc["branch_id"]:
                    cur_idx = i
        sel = c1.selectbox("شعبه", branch_labels, index=cur_idx)
        doc_date = c2.text_input("تاریخ سند", value=doc["doc_date"] if doc else services.today_jalali())
        note = c3.text_input("توضیحات سند", value=doc["note"] if doc else "")

        st.markdown(f"**اقلام سند (حداکثر {config.MAX_ITEMS} ردیف — برای چاپ یک‌صفحه‌ای)**")
        if doc and doc["items"]:
            data = [{
                "item_date": it["item_date"], "title": it["title"],
                "insurance": it["insurance"], "tax": it["tax"], "amount": it["amount"],
            } for it in doc["items"]]
        else:
            data = [{"item_date": services.today_jalali(), "title": "", "insurance": 0.0,
                     "tax": 0.0, "amount": 0.0}]
        df = pd.DataFrame(data, columns=["item_date", "title", "insurance", "tax", "amount"])
        edited = st.data_editor(
            df, num_rows="dynamic", use_container_width=True, key="items_editor",
            column_config={
                "item_date": st.column_config.TextColumn("تاریخ", width="small"),
                "title": st.column_config.TextColumn("شرح هزینه (عنوان)", width="large"),
                "insurance": st.column_config.NumberColumn("بیمه (ریال)", min_value=0.0, format="%.0f"),
                "tax": st.column_config.NumberColumn("مالیات (ریال)", min_value=0.0, format="%.0f"),
                "amount": st.column_config.NumberColumn("مبلغ (ریال)", min_value=0.0, format="%.0f"),
            },
        )
        items = edited.to_dict("records")
        totals = services.doc_totals([i for i in items if str(i.get("title") or "").strip()])
        st.caption(f"جمع بیمه: {fmt_money(totals['insurance'])} | جمع مالیات: {fmt_money(totals['tax'])} | "
                   f"جمع مبلغ: {fmt_money(totals['amount'])} | **جمع کل: {fmt_money(totals['total'])} ریال**")

        b1, b2, b3 = st.columns([1, 1, 2])
        save_draft = b1.form_submit_button("💾 ذخیره پیش‌نویس", use_container_width=True)
        do_finalize = b2.form_submit_button("✅ نهایی‌کردن", type="primary", use_container_width=True)

    if save_draft or do_finalize:
        try:
            for w in services.overflow_warnings([i for i in items if str(i.get("title") or "").strip()]):
                st.warning(w)
            branch_id = branches[branch_labels.index(sel)]["id"]
            if is_new:
                doc_id = services.create_document(user["id"], branch_id, doc_date, note, items)
                action = "create_document"
            else:
                doc_id = doc["id"]
                services.update_document(doc_id, user["id"], branch_id, doc_date, note, items)
                action = "update_document"
            services.audit(user, action, "documents", doc_id, f"تاریخ={doc_date}، شعبه={sel}")
            if do_finalize:
                doc_number = services.finalize_document(doc_id, user["id"])
                services.audit(user, "finalize_document", "documents", doc_id, f"شماره سند: {doc_number}")
                st.success(f"سند نهایی شد. شماره سند: **{doc_number}**")
                st.session_state["print_doc"] = doc_id
                st.session_state.pop("edit_doc", None)
                st.rerun()
            else:
                st.success("پیش‌نویس ذخیره شد.")
                st.session_state.pop("edit_doc", None)
                st.rerun()
        except ValueError as e:
            st.error(str(e))

    if st.button("بازگشت"):
        st.session_state.pop("edit_doc")
        st.rerun()


def _print_view(doc_id: int) -> None:
    user = st.session_state["user"]
    doc = services.get_document(doc_id)
    if not doc:
        st.error("سند یافت نشد.")
        st.session_state.pop("print_doc")
        return

    st.title("🖨 چاپ سند")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
    if c1.button("⬅ بازگشت"):
        st.session_state.pop("print_doc")
        st.rerun()

    settings = {}
    with db.connect() as conn:
        for r in conn.execute("SELECT key, value FROM settings"):
            settings[r["key"]] = r["value"]

    tanakhah = services.tanakhah_summary(doc["branch_id"])
    html_doc = printing.build_print_html(doc, tanakhah, settings)

    # هشدار یک‌صفحه‌ای بودن (قاعده: هشدار بده)
    for w in services.overflow_warnings(doc["items"]):
        st.warning(w)

    is_final = doc["status"] == "final"
    if c2.button("🖨 چاپ", type="primary", disabled=not is_final and doc["status"] == "void"):
        services.bump_print_count(doc_id)
        services.audit(user, "print_document", "documents", doc_id, doc["doc_number"] or "پیش‌نویس")

    st.download_button(
        "⬇ دانلود فایل چاپی (HTML)",
        data=html_doc.encode("utf-8"),
        file_name=f"senad-{(doc['doc_number'] or str(doc_id)).replace('/', '-')}.html",
        mime="text/html",
        help="فایل را در مرورگر باز کنید و Ctrl+P بزنید — دقیقاً یک صفحه A4 چاپ می‌شود.",
    )

    if doc["status"] == "draft":
        st.info("این سند پیش‌نویس است (واترمارک روی چاپ). پس از «نهایی‌کردن»، شماره سند قطعی می‌شود.")
        if config.can(user["role"], "finalize") and (user["role"] != "karperdaz" or doc["created_by"] == user["id"]):
            if st.button("✅ نهایی‌کردن سند"):
                try:
                    num = services.finalize_document(doc_id, user["id"])
                    services.audit(user, "finalize_document", "documents", doc_id, num)
                    st.success(f"سند نهایی شد: {num}")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    if doc["status"] != "void" and config.can(user["role"], "void"):
        with st.expander("⛔ ابطال سند"):
            reason = st.text_input("دلیل ابطال (الزامی)")
            if st.button("تأیید ابطال"):
                try:
                    services.void_document(doc_id, user["id"], reason)
                    services.audit(user, "void_document", "documents", doc_id, f"دلیل: {reason}")
                    st.warning("سند باطل شد.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    st.divider()
    components.html(html_doc, height=1250, scrolling=True)
