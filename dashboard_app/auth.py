from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from dashboard_app.config import MAX_USERS, ROLE_CODES
from dashboard_app.database import db_connection, utc_now, write_audit

PBKDF2_ITERATIONS = 310_000
MIN_PASSWORD_LENGTH = 12
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")


def user_count() -> int:
    with db_connection() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def get_active_user(username: str) -> dict[str, str] | None:
    with db_connection() as connection:
        user = connection.execute(
            "SELECT username, display_name, role FROM users WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
    return dict(user) if user else None


def _validate_username(username: str) -> str:
    value = username.strip()
    if not _USERNAME_RE.fullmatch(value):
        raise ValueError(
            "نام کاربری باید ۳ تا ۳۲ نویسه و شامل حروف لاتین، عدد، نقطه، خط تیره یا زیرخط باشد."
        )
    return value


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"گذرواژه باید دست‌کم {MIN_PASSWORD_LENGTH} نویسه باشد.")
    if len(password) > 256:
        raise ValueError("گذرواژه بیش از حد طولانی است.")


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    _validate_password(password)
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32
    )
    return salt.hex(), digest.hex()


def _verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        actual_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32
        ).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual_hash, expected_hash)


def create_initial_admin(username: str, display_name: str, password: str) -> None:
    username = _validate_username(username)
    display_name = display_name.strip() or username
    salt, password_hash = _hash_password(password)
    now = utc_now()
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        count = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        if count:
            connection.rollback()
            raise ValueError("حساب مدیر اولیه قبلاً ساخته شده است.")
        connection.execute(
            """INSERT INTO users(
                   username, display_name, role, password_salt, password_hash,
                   is_active, created_by, created_at
               ) VALUES (?, ?, 'admin', ?, ?, 1, 'system', ?)""",
            (username, display_name, salt, password_hash, now),
        )
        write_audit(
            connection, username, "bootstrap_admin", "user", username, {"role": "admin"}
        )
        connection.commit()


def authenticate(username: str, password: str) -> dict[str, str] | None:
    normalized = username.strip()[:64]
    now = datetime.now(timezone.utc)
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        user = connection.execute(
            """SELECT username, display_name, role, password_salt, password_hash,
                      is_active, failed_attempts, locked_until
               FROM users WHERE username = ? COLLATE NOCASE""",
            (normalized,),
        ).fetchone()
        if user is None or not bool(user["is_active"]):
            # Avoid a cheap username-existence timing signal.
            dummy_salt = "9c6a7a6c0ecf6b17b50f4408c09b1a0c"
            _verify_password(password[:256], dummy_salt, "0" * 64)
            write_audit(
                connection,
                normalized or "unknown",
                "login_failed",
                "auth",
                details={"reason": "invalid_credentials"},
            )
            connection.commit()
            return None

        locked_until = user["locked_until"]
        if locked_until:
            try:
                if datetime.fromisoformat(locked_until) > now:
                    write_audit(
                        connection,
                        user["username"],
                        "login_blocked",
                        "auth",
                        details={"reason": "lockout"},
                    )
                    connection.commit()
                    return None
            except ValueError:
                pass

        if not _verify_password(
            password[:256], user["password_salt"], user["password_hash"]
        ):
            attempts = int(user["failed_attempts"]) + 1
            lock_until = None
            if attempts >= MAX_LOGIN_ATTEMPTS:
                lock_until = (now + timedelta(minutes=LOCKOUT_MINUTES)).isoformat(
                    timespec="seconds"
                )
                attempts = 0
            connection.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE username = ?",
                (attempts, lock_until, user["username"]),
            )
            write_audit(
                connection,
                user["username"],
                "login_failed",
                "auth",
                details={"locked": lock_until is not None},
            )
            connection.commit()
            return None

        connection.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE username = ?",
            (user["username"],),
        )
        write_audit(connection, user["username"], "login_success", "auth")
        connection.commit()
        return {
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
        }


def list_users() -> list[dict[str, Any]]:
    with db_connection() as connection:
        rows = connection.execute(
            """SELECT username, display_name, role, is_active, created_by, created_at,
                      updated_at, failed_attempts, locked_until
               FROM users ORDER BY username COLLATE NOCASE"""
        ).fetchall()
    return [dict(row) for row in rows]


def create_user(
    username: str,
    display_name: str,
    password: str,
    role: str,
    actor: str,
) -> None:
    username = _validate_username(username)
    _validate_password(password)
    if role not in ROLE_CODES:
        raise ValueError("نقش انتخاب‌شده معتبر نیست.")
    display_name = display_name.strip() or username
    salt, password_hash = _hash_password(password)
    now = utc_now()
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        active_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM users WHERE is_active = 1"
            ).fetchone()[0]
        )
        if active_count >= MAX_USERS:
            connection.rollback()
            raise ValueError(f"این سامانه حداکثر {MAX_USERS} حساب فعال می‌پذیرد.")
        connection.execute(
            """INSERT INTO users(
                   username, display_name, role, password_salt, password_hash,
                   is_active, created_by, created_at
               ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
            (username, display_name, role, salt, password_hash, actor, now),
        )
        write_audit(connection, actor, "create", "user", username, {"role": role})
        connection.commit()


def reset_user_password(username: str, new_password: str, actor: str) -> None:
    _validate_password(new_password)
    salt, password_hash = _hash_password(new_password)
    now = utc_now()
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT username FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            connection.rollback()
            raise ValueError("کاربر پیدا نشد.")
        connection.execute(
            """UPDATE users SET password_salt = ?, password_hash = ?,
                      failed_attempts = 0, locked_until = NULL, updated_at = ?
               WHERE username = ?""",
            (salt, password_hash, now, username),
        )
        write_audit(connection, actor, "reset_password", "user", username)
        connection.commit()


def set_user_active(username: str, active: bool, actor: str) -> None:
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        target = connection.execute(
            "SELECT username, role, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if target is None:
            connection.rollback()
            raise ValueError("کاربر پیدا نشد.")
        if not active and target["role"] == "admin" and bool(target["is_active"]):
            active_admins = int(
                connection.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
                ).fetchone()[0]
            )
            if active_admins <= 1:
                connection.rollback()
                raise ValueError("نمی‌توان آخرین مدیر فعال را غیرفعال کرد.")
        connection.execute(
            "UPDATE users SET is_active = ?, updated_at = ? WHERE username = ?",
            (1 if active else 0, utc_now(), username),
        )
        write_audit(
            connection,
            actor,
            "activate_user" if active else "deactivate_user",
            "user",
            username,
        )
        connection.commit()


def change_own_password(username: str, old_password: str, new_password: str) -> None:
    _validate_password(new_password)
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        user = connection.execute(
            "SELECT password_salt, password_hash FROM users WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()
        if user is None or not _verify_password(
            old_password[:256], user["password_salt"], user["password_hash"]
        ):
            connection.rollback()
            raise ValueError("گذرواژهٔ فعلی درست نیست.")
        salt, password_hash = _hash_password(new_password)
        connection.execute(
            """UPDATE users SET password_salt = ?, password_hash = ?,
                      failed_attempts = 0, locked_until = NULL, updated_at = ?
               WHERE username = ?""",
            (salt, password_hash, utc_now(), username),
        )
        write_audit(connection, username, "change_password", "user", username)
        connection.commit()
