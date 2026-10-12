"""منطق برنامه: تاریخ شمسی، اسناد، شماره‌گذاری، تنخواه، لاگ و بکاپ."""
import html
import shutil
from datetime import datetime
from pathlib import Path

import jdatetime

from . import config, db

# ---------- تاریخ شمسی ----------

def today_jalali() -> str:
    return jdatetime.date.today().strftime("%Y/%m/%d")


def parse_jalali(value: str) -> jdatetime.date | None:
    value = (value or "").strip().replace("-", "/").replace(".", "/")
    for fmt in ("%Y/%m/%d", "%Y/%m/%d"):
        try:
            return jdatetime.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    # اگر ارقام فارسی بود
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    try:
        return jdatetime.datetime.strptime(value.translate(trans), "%Y/%m/%d").date()
    except ValueError:
        return None


def date_key(value: str) -> int:
    d = parse_jalali(value)
    return d.year * 10000 + d.month * 100 + d.day if d else 0


def jalali_year(value: str) -> int:
    d = parse_jalali(value)
    return d.year if d else 0


def to_int_digits(value: str) -> str:
    return (value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")).strip()


# ---------- شعب ----------

def list_branches(active_only: bool = False) -> list[dict]:
    q = "SELECT * FROM branches"
    if active_only:
        q += " WHERE is_active=1"
    q += " ORDER BY code"
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(q).fetchall()]


def add_branch(code: str, name: str) -> None:
    code = to_int_digits(code).strip()
    if not (code.isdigit() and len(code) == 2):
        raise ValueError("کد شعبه باید دقیقاً دو رقم باشد (مثال: 45)")
    if not name.strip():
        raise ValueError("نام شعبه الزامی است")
    with db.connect() as conn:
        conn.execute("INSERT INTO branches(code, name) VALUES (?,?)", (code, name.strip()))


def update_branch(branch_id: int, code: str, name: str, is_active: int) -> None:
    code = to_int_digits(code).strip()
    if not (code.isdigit() and len(code) == 2):
        raise ValueError("کد شعبه باید دقیقاً دو رقم باشد")
    with db.connect() as conn:
        conn.execute(
            "UPDATE branches SET code=?, name=?, is_active=? WHERE id=?",
            (code, name.strip(), is_active, branch_id),
        )


def get_branch(branch_id: int) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM branches WHERE id=?", (branch_id,)).fetchone()
    return dict(row) if row else None


# ---------- اسناد ----------

def doc_totals(items: list[dict]) -> dict:
    ins = sum(float(i.get("insurance") or 0) for i in items)
    tax = sum(float(i.get("tax") or 0) for i in items)
    amt = sum(float(i.get("amount") or 0) for i in items)
    return {"insurance": ins, "tax": tax, "amount": amt, "total": ins + tax + amt}


def validate_items(items: list[dict]) -> list[dict]:
    cleaned = []
    for i, it in enumerate(items, start=1):
        title = str(it.get("title") or "").strip()
        if not title:
            continue  # ردیف کاملاً خالی رد می‌شود
        cleaned.append({
            "row_no": len(cleaned) + 1,
            "item_date": to_int_digits(str(it.get("item_date") or "")).replace("-", "/"),
            "title": title,
            "insurance": float(it.get("insurance") or 0),
            "tax": float(it.get("tax") or 0),
            "amount": float(it.get("amount") or 0),
        })
    if not cleaned:
        raise ValueError("حداقل یک ردیف با عنوان الزامی است")
    if len(cleaned) > config.MAX_ITEMS:
        raise ValueError(f"حداکثر {config.MAX_ITEMS} ردیف در هر سند مجاز است (برای چاپ یک‌صفحه‌ای)")
    for it in cleaned:
        for f in ("insurance", "tax", "amount"):
            if it[f] < 0:
                raise ValueError("مقادیر مالی نمی‌توانند منفی باشند")
        if it["item_date"] and parse_jalali(it["item_date"]) is None:
            raise ValueError(f"تاریخ ردیف {it['row_no']} نامعتبر است (مثال: 1405/07/18)")
    return cleaned


def overflow_warnings(items: list[dict]) -> list[str]:
    """هشدار محتوای بیش از حد برای حفظ چاپ یک‌صفحه‌ای (قاعده ۴: هشدار بده)."""
    warns = []
    long_titles = [it["row_no"] for it in items if len(it["title"]) > 70]
    if long_titles:
        warns.append(f"شرح ردیف‌های {long_titles} بلند است؛ ممکن است چاپ از یک صفحه خارج شود.")
    if len(items) == config.MAX_ITEMS and any(len(it["title"]) > 40 for it in items):
        warns.append("تعداد ردیف‌ها حداکثر است و برخی شرح‌ها بلندند؛ احتمال خروج از یک صفحه چاپ وجود دارد.")
    return warns


def create_document(user_id: int, branch_id: int, doc_date: str, note: str, items: list[dict]) -> int:
    if parse_jalali(doc_date) is None:
        raise ValueError("تاریخ سند نامعتبر است (مثال: 1405/07/18)")
    cleaned = validate_items(items)
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO documents(branch_id, doc_date, date_key, status, note, created_by) "
            "VALUES (?,?,?,'draft',?,?)",
            (branch_id, to_int_digits(doc_date).replace("-", "/"), date_key(doc_date), note.strip(), user_id),
        )
        doc_id = cur.lastrowid
        _insert_items(conn, doc_id, cleaned)
    return doc_id


def update_document(doc_id: int, user_id: int, branch_id: int, doc_date: str, note: str,
                    items: list[dict]) -> None:
    if parse_jalali(doc_date) is None:
        raise ValueError("تاریخ سند نامعتبر است")
    cleaned = validate_items(items)
    with db.connect() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("سند یافت نشد")
        if doc["status"] == "void":
            raise ValueError("سند باطل‌شده قابل ویرایش نیست")
        conn.execute(
            "UPDATE documents SET branch_id=?, doc_date=?, date_key=?, note=?, "
            "updated_at=datetime('now','localtime'), updated_by=? WHERE id=?",
            (branch_id, to_int_digits(doc_date).replace("-", "/"), date_key(doc_date),
             note.strip(), user_id, doc_id),
        )
        conn.execute("DELETE FROM doc_items WHERE doc_id=?", (doc_id,))
        _insert_items(conn, doc_id, cleaned)


def _insert_items(conn, doc_id: int, items: list[dict]) -> None:
    for it in items:
        conn.execute(
            "INSERT INTO doc_items(doc_id, row_no, item_date, title, insurance, tax, amount) "
            "VALUES (?,?,?,?,?,?,?)",
            (doc_id, it["row_no"], it["item_date"], it["title"], it["insurance"], it["tax"], it["amount"]),
        )


def finalize_document(doc_id: int, user_id: int) -> str:
    """نهایی‌کردن سند + تخصیص شماره (کدشعبه-سال-عدد)."""
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("سند یافت نشد")
        if doc["status"] != "draft":
            raise ValueError("فقط سند پیش‌نویس قابل نهایی‌شدن است")
        items = conn.execute("SELECT * FROM doc_items WHERE doc_id=?", (doc_id,)).fetchall()
        if not items:
            raise ValueError("سند بدون ردیف قابل نهایی‌شدن نیست")
        branch = conn.execute("SELECT * FROM branches WHERE id=?", (doc["branch_id"],)).fetchone()
        year = jalali_year(doc["doc_date"])
        if not year:
            raise ValueError("سال سند نامعتبر است")
        row = conn.execute(
            "SELECT last_seq FROM branch_seq WHERE branch_id=? AND year=?",
            (doc["branch_id"], year),
        ).fetchone()
        seq = (row["last_seq"] + 1) if row else 1
        if row:
            conn.execute(
                "UPDATE branch_seq SET last_seq=? WHERE branch_id=? AND year=?",
                (seq, doc["branch_id"], year),
            )
        else:
            conn.execute(
                "INSERT INTO branch_seq(branch_id, year, last_seq) VALUES (?,?,?)",
                (doc["branch_id"], year, seq),
            )
        sep_row = conn.execute("SELECT value FROM settings WHERE key='number_separator'").fetchone()
        sep = sep_row["value"] if sep_row and sep_row["value"] else "-"
        width_row = conn.execute("SELECT value FROM settings WHERE key='seq_width'").fetchone()
        width = int(width_row["value"] or 4) if width_row else 4
        doc_number = f"{branch['code']}{sep}{year}{sep}{seq:0{width}d}"
        conn.execute(
            "UPDATE documents SET doc_number=?, doc_year=?, seq=?, status='final', "
            "finalized_at=datetime('now','localtime'), finalized_by=? WHERE id=?",
            (doc_number, year, seq, user_id, doc_id),
        )
        return doc_number


def void_document(doc_id: int, user_id: int, reason: str) -> None:
    if not (reason or "").strip():
        raise ValueError("دلیل ابطال الزامی است")
    with db.connect() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("سند یافت نشد")
        if doc["status"] == "void":
            raise ValueError("این سند قبلاً باطل شده است")
        conn.execute(
            "UPDATE documents SET status='void', voided_at=datetime('now','localtime'), "
            "voided_by=?, void_reason=? WHERE id=?",
            (user_id, reason.strip(), doc_id),
        )


def get_document(doc_id: int) -> dict | None:
    with db.connect() as conn:
        doc = conn.execute(
            "SELECT d.*, b.code AS branch_code, b.name AS branch_name, "
            "u.full_name AS creator_name FROM documents d "
            "JOIN branches b ON b.id=d.branch_id "
            "JOIN users u ON u.id=d.created_by WHERE d.id=?",
            (doc_id,),
        ).fetchone()
        if not doc:
            return None
        result = dict(doc)
        result["items"] = [dict(r) for r in conn.execute(
            "SELECT * FROM doc_items WHERE doc_id=? ORDER BY row_no", (doc_id,)
        ).fetchall()]
        result["totals"] = doc_totals(result["items"])
        return result


def list_documents(branch_ids: list[int] | None = None, status: str = "",
                   date_from: str = "", date_to: str = "", search: str = "",
                   created_by: int | None = None, limit: int = 500) -> list[dict]:
    q = ("SELECT d.id, d.doc_number, d.doc_date, d.status, d.note, d.print_count, "
         "b.code AS branch_code, b.name AS branch_name, u.full_name AS creator_name, "
         "(SELECT SUM(insurance+tax+amount) FROM doc_items WHERE doc_id=d.id) AS total "
         "FROM documents d JOIN branches b ON b.id=d.branch_id "
         "JOIN users u ON u.id=d.created_by WHERE 1=1")
    params: list = []
    if branch_ids is not None:
        if not branch_ids:
            return []
        q += f" AND d.branch_id IN ({','.join('?' * len(branch_ids))})"
        params += branch_ids
    if status:
        q += " AND d.status=?"
        params.append(status)
    if created_by:
        q += " AND d.created_by=?"
        params.append(created_by)
    if date_from and parse_jalali(date_from):
        q += " AND d.date_key>=?"
        params.append(date_key(date_from))
    if date_to and parse_jalali(date_to):
        q += " AND d.date_key<=?"
        params.append(date_key(date_to))
    if search:
        q += " AND (d.doc_number LIKE ? OR d.note LIKE ? OR EXISTS (SELECT 1 FROM doc_items i WHERE i.doc_id=d.id AND i.title LIKE ?))"
        like = f"%{search.strip()}%"
        params += [like, like, like]
    q += " ORDER BY d.date_key DESC, d.id DESC LIMIT ?"
    params.append(limit)
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def bump_print_count(doc_id: int) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE documents SET print_count=print_count+1 WHERE id=?", (doc_id,))


# ---------- تنخواه ----------

def add_tanakhah(user_id: int, branch_id: int, tx_date: str, amount: float, description: str) -> int:
    if parse_jalali(tx_date) is None:
        raise ValueError("تاریخ واریز نامعتبر است")
    if amount <= 0:
        raise ValueError("مبلغ واریز باید بزرگ‌تر از صفر باشد")
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO tanakhah_tx(branch_id, tx_date, date_key, amount, description, created_by) "
            "VALUES (?,?,?,?,?,?)",
            (branch_id, to_int_digits(tx_date).replace("-", "/"), date_key(tx_date),
             float(amount), description.strip(), user_id),
        )
        return cur.lastrowid


def delete_tanakhah(tx_id: int) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM tanakhah_tx WHERE id=?", (tx_id,))


def list_tanakhah(branch_id: int | None = None) -> list[dict]:
    q = ("SELECT t.*, b.code AS branch_code, b.name AS branch_name, u.full_name AS creator_name "
         "FROM tanakhah_tx t JOIN branches b ON b.id=t.branch_id "
         "JOIN users u ON u.id=t.created_by")
    params: list = []
    if branch_id:
        q += " WHERE t.branch_id=?"
        params.append(branch_id)
    q += " ORDER BY t.date_key DESC, t.id DESC"
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def tanakhah_summary(branch_id: int) -> dict:
    """مانده = مجموع دریافتی‌ها − مجموع کل اسناد نهایی (مبلغ+بیمه+مالیات)."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS total_in, MAX(tx_date) AS last_date "
            "FROM tanakhah_tx WHERE branch_id=?", (branch_id,)
        ).fetchone()
        docs = conn.execute(
            "SELECT COALESCE(SUM(i.insurance+i.tax+i.amount),0) AS total_docs "
            "FROM doc_items i JOIN documents d ON d.id=i.doc_id "
            "WHERE d.branch_id=? AND d.status='final'", (branch_id,)
        ).fetchone()
    total_in = float(row["total_in"] or 0)
    total_docs = float(docs["total_docs"] or 0)
    return {
        "total_in": total_in,
        "total_docs": total_docs,
        "balance": total_in - total_docs,
        "last_date": row["last_date"] or "",
    }


# ---------- لاگ ----------

def audit(user: dict | None, action: str, entity: str = "", entity_id: str = "", details: str = "") -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO audit_log(user_id, username, action, entity, entity_id, details) "
            "VALUES (?,?,?,?,?,?)",
            (user.get("id") if user else None, user.get("username", "") if user else "",
             action, entity, str(entity_id), html.escape(details)[:2000]),
        )


def list_log(limit: int = 300) -> list[dict]:
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()]


# ---------- بکاپ ----------

def backup_now(tag: str = "auto") -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = config.BACKUP_DIR / f"senad-{ts}-{tag}.db"
    shutil.copy2(config.DB_PATH, target)
    db.set_setting("last_backup_at", datetime.now().isoformat(timespec="seconds"))
    # نگهداری حداکثر ۳۰ نسخه اخیر
    backups = sorted(config.BACKUP_DIR.glob("senad-*.db"))
    for old in backups[:-30]:
        try:
            old.unlink()
        except OSError:
            pass
    return target


def auto_backup_if_due() -> Path | None:
    last = db.get_setting("last_backup_at", "")
    today = datetime.now().strftime("%Y%m%d")
    if not last.startswith(today):
        return backup_now("auto")
    return None


def list_backups() -> list[dict]:
    rows = []
    for p in sorted(config.BACKUP_DIR.glob("senad-*.db"), reverse=True):
        rows.append({"name": p.name, "size": p.stat().st_size, "path": p})
    return rows


# ---------- گزارش ----------

def dashboard_stats(branch_ids: list[int] | None) -> dict:
    tk = date_key(today_jalali())
    month_prefix = tk // 100
    month_start, month_end = month_prefix * 100 + 1, month_prefix * 100 + 31

    where, params = "1=1", []
    if branch_ids is not None:
        if not branch_ids:
            return {"today_count": 0, "month_count": 0, "month_total": 0.0, "draft_count": 0}
        where += f" AND branch_id IN ({','.join('?' * len(branch_ids))})"
        params += branch_ids

    with db.connect() as conn:
        today_count = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE {where} AND date_key=?",
            params + [tk]).fetchone()[0]
        month_count = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE {where} AND date_key BETWEEN ? AND ?",
            params + [month_start, month_end]).fetchone()[0]
        month_total = conn.execute(
            f"SELECT COALESCE(SUM(i.insurance+i.tax+i.amount),0) FROM doc_items i "
            f"JOIN documents d ON d.id=i.doc_id WHERE {where.replace('branch_id', 'd.branch_id')} "
            f"AND d.date_key BETWEEN ? AND ?",
            params + [month_start, month_end]).fetchone()[0]
        draft_count = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE {where} AND status='draft'",
            params).fetchone()[0]
    return {"today_count": today_count, "month_count": month_count,
            "month_total": float(month_total or 0), "draft_count": draft_count}
