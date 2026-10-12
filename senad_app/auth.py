"""کاربران، احراز هویت و نقش‌ها."""
import hashlib
import os

from . import config, db

_ITERATIONS = 200_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _ITERATIONS
        )
        return digest.hex() == digest_hex
    except Exception:
        return False


def has_users() -> bool:
    with db.connect() as conn:
        return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def authenticate(username: str, password: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1", (username.strip(),)
        ).fetchone()
    if row and verify_password(password, row["password_hash"]):
        return dict(row)
    return None


def create_user(username: str, password: str, full_name: str, role: str) -> int:
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO users(username, password_hash, full_name, role) VALUES (?,?,?,?)",
            (username.strip(), hash_password(password), full_name.strip(), role),
        )
        return cur.lastrowid


def update_user(user_id: int, full_name: str, role: str, is_active: int) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET full_name=?, role=?, is_active=? WHERE id=?",
            (full_name.strip(), role, is_active, user_id),
        )


def reset_password(user_id: int, password: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(password), user_id),
        )


def list_users() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, username, full_name, role, is_active, created_at FROM users ORDER BY id"
        ).fetchall()
        result = []
        for r in rows:
            u = dict(r)
            u["branches"] = conn.execute(
                "SELECT b.id, b.code, b.name FROM branches b "
                "JOIN user_branch ub ON ub.branch_id=b.id WHERE ub.user_id=? ORDER BY b.code",
                (r["id"],),
            ).fetchall()
            result.append(u)
        return result


def set_user_branches(user_id: int, branch_ids: list[int]) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM user_branch WHERE user_id=?", (user_id,))
        for bid in branch_ids:
            conn.execute(
                "INSERT OR IGNORE INTO user_branch(user_id, branch_id) VALUES (?,?)",
                (user_id, bid),
            )


def user_branch_ids(user_id: int, role: str) -> list[int] | None:
    """None یعنی همه شعب (مدیر/سرپرست)."""
    if config.can(role, "view_all"):
        return None
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT branch_id FROM user_branch WHERE user_id=?", (user_id,)
        ).fetchall()
    return [r["branch_id"] for r in rows]
