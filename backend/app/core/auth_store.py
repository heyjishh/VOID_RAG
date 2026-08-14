"""Async DB helpers for the auth router — thin, explicit CRUD over the models.

Avoids a FastAPI session-dependency layer on purpose: every function opens and
closes its own session so auth flows (which don't interleave with the retrieval
graph) stay self-contained and trivially testable.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.config.settings import settings
from app.core.db import get_sessionmaker
from app.core.security import hash_password, new_otp, new_token
from app.models.auth import AuthSession, OtpCode, User

_UNIQUE_OTP: dict[str, object] = {}  # (channel, target, purpose) -> created_at (in-mem throttle)


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    return email.strip().lower()


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"[^\d]", "", phone)
    return digits[-15:] if digits else None


def mask_target(channel: str, target: str) -> str:
    if channel == "email":
        local, _, domain = target.partition("@")
        if not domain:
            return "*" * len(target)
        keep = local[:2] + "*" * max(0, len(local) - 2)
        return f"{keep}@{domain}"
    return "*" * max(0, len(target) - 4) + target[-4:]


async def get_user_by_email(email: str) -> User | None:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                select(User).where(User.email == normalize_email(email))
            )
        ).scalar_one_or_none()


async def get_user_by_phone(phone: str) -> User | None:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(select(User).where(User.phone == normalize_phone(phone)))
        ).scalar_one_or_none()


async def create_user(
    *,
    name: str,
    email: str | None = None,
    phone: str | None = None,
    password: str | None = None,
    email_verified: bool = False,
    phone_verified: bool = False,
    org: str = "",
) -> User:
    user = User(
        name=name.strip() or "Researcher",
        email=normalize_email(email),
        phone=normalize_phone(phone),
        password_hash=hash_password(password) if password else None,
        email_verified=email_verified,
        phone_verified=phone_verified,
        org=org.strip() or "",
    )
    async with get_sessionmaker()() as s:
        s.add(user)
        await s.commit()
        await s.refresh(user)
    return user


async def update_user(user: User, **fields):
    async with get_sessionmaker()() as s:
        obj = await s.get(User, user.id)
        for k, v in fields.items():
            setattr(obj, k, v)
        await s.commit()
        await s.refresh(obj)
    return obj


async def set_password(user: User, plaintext: str) -> User:
    return await update_user(user, password_hash=hash_password(plaintext))


async def create_session(user_id: int) -> str:
    token = new_token()
    session = AuthSession(
        user_id=user_id,
        token=token,
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.AUTH_SESSION_TTL_SECONDS),
    )
    async with get_sessionmaker()() as s:
        s.add(session)
        await s.commit()
    return token


async def get_user_by_session(token: str) -> User | None:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                select(AuthSession, User)
                .join(User, User.id == AuthSession.user_id)
                .where(AuthSession.token == token, AuthSession.revoked.is_(False))
            )
        ).first()
        if not row:
            return None
        session, user = row
        if session.expires_at <= datetime.now(timezone.utc):
            return None
        if not user.is_active:
            return None
        return user


async def revoke_session(token: str) -> bool:
    async with get_sessionmaker()() as s:
        result = await s.execute(delete(AuthSession).where(AuthSession.token == token))
        await s.commit()
        return result.rowcount > 0


async def can_send_otp(channel: str, target: str, purpose: str) -> float:
    """Seconds remaining before the target can be sent another OTP (0 = allowed)."""
    key = (channel, target, purpose)
    last = _UNIQUE_OTP.get(key)
    if last is None:
        return 0.0
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    remaining = settings.AUTH_OTP_MIN_INTERVAL_SECONDS - elapsed
    return max(remaining, 0.0)


async def mark_otp_sent(channel: str, target: str, purpose: str):
    _UNIQUE_OTP[(channel, target, purpose)] = datetime.now(timezone.utc)


async def store_otp(channel: str, target: str, purpose: str, ttl_seconds: int | None = None) -> str:
    """Invalidate prior unconsumed codes for the target+purpose, store a fresh one."""
    code = new_otp(settings.AUTH_OTP_LENGTH)
    ttl = ttl_seconds or settings.AUTH_OTP_TTL_SECONDS
    async with get_sessionmaker()() as s:
        await s.execute(
            delete(OtpCode).where(
                OtpCode.channel == channel,
                OtpCode.target == target,
                OtpCode.purpose == purpose,
                OtpCode.consumed.is_(False),
            )
        )
        s.add(
            OtpCode(
                purpose=purpose,
                channel=channel,
                target=target,
                code_hash=hash_password(code),  # PBKDF2 for the 6-digit code too
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
            )
        )
        await s.commit()
    return code


async def consume_otp(channel: str, target: str, purpose: str, code: str) -> str | None:
    """Validate + consume a code. Returns its original (plaintext) value on success."""
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                select(OtpCode)
                .where(
                    OtpCode.channel == channel,
                    OtpCode.target == target,
                    OtpCode.purpose == purpose,
                    OtpCode.consumed.is_(False),
                )
                .order_by(OtpCode.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not row:
            return None
        if row.expires_at <= datetime.now(timezone.utc):
            return None
        row.attempts += 1
        if row.attempts > settings.AUTH_OTP_MAX_ATTEMPTS:
            row.consumed = True
            await s.commit()
            return None
        from app.core.security import verify_password

        if not verify_password(code, row.code_hash):
            await s.commit()
            return None
        row.consumed = True
        await s.commit()
        return code


def user_to_out(user: User) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "org": user.org,
        "email_verified": user.email_verified,
        "phone_verified": user.phone_verified,
    }