"""Authentication API — password login, email/phone OTP, forgot-reset.

Flows (all return clean JSON; the frontend drives the step UI)::

    POST /auth/otp/send     {via, email|phone, intent, name?}
    POST /auth/otp/verify   {via, email|phone, otp, intent, name?}
    POST /auth/register     {name, email|phone, password}
    POST /auth/login        {email|phone, password}
    POST /auth/forgot       {via, email|phone}          (alias of otp/send, intent=reset)
    POST /auth/reset        {via, email|phone, otp, new_password}
    GET  /auth/me           (Bearer)
    POST /auth/logout       (Bearer)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.schemas import (
    AuthResponse,
    AuthUserOut,
    ForgotRequest,
    LoginRequest,
    OtpSendRequest,
    OtpSendResponse,
    OtpVerifyRequest,
    OtpVerifySuccessOut,
    RegisterRequest,
    ResetRequest,
)
from app.config.settings import settings
from app.core import auth_store as store
from app.core import notify
from app.core.security import verify_password
from app.models.auth import User

logger = logging.getLogger("juryai.auth")

router = APIRouter()


def _resolve_target(via: str, email: str | None, phone: str | None) -> tuple[str, str]:
    via = via.strip().lower()
    if via == "email":
        target = store.normalize_email(email)
        if not target:
            raise HTTPException(400, "Email is required for via=email.")
        return "email", target
    if via == "phone":
        target = store.normalize_phone(phone)
        if not target:
            raise HTTPException(400, "Phone number is required for via=phone.")
        return "phone", target
    raise HTTPException(400, 'via must be "email" or "phone".')


async def _send_otp(via: str, email: str | None, phone: str | None, intent: str, name: str | None) -> dict:
    if intent not in ("signup", "login", "reset"):
        raise HTTPException(400, 'intent must be "signup", "login" or "reset".')
    channel, target = _resolve_target(via, email, phone)

    user = (
        await store.get_user_by_email(target)
        if channel == "email"
        else await store.get_user_by_phone(target)
    )
    exists = user is not None
    if intent == "signup" and exists:
        raise HTTPException(409, "An account already exists for this identity. Sign in instead.")
    if intent in ("login", "reset") and not exists:
        raise HTTPException(404, "No account found for this identity. Create one first.")

    wait = await store.can_send_otp(channel, target, intent)
    if wait > 0:
        raise HTTPException(429, f"Please wait {int(wait) + 1}s before requesting another code.")

    code = await store.store_otp(channel, target, intent)
    await store.mark_otp_sent(channel, target, intent)

    if channel == "email":
        delivery = await notify.send_email_otp(target, code)
    else:
        delivery = await notify.send_sms_otp(target, code)

    logger.info("OTP requested channel=%s intent=%s target=%s delivery=%s", channel, intent, target, delivery)
    return {
        "sent": True,
        "delivery": delivery,
        "target": store.mask_target(channel, target),
        "dev_otp": code if delivery == "dev" else None,
        "expires_in": settings.AUTH_OTP_TTL_SECONDS,
        "exists": exists,
    }


@router.post("/auth/otp/send", response_model=OtpSendResponse)
async def auth_otp_send(request: OtpSendRequest):
    return await _send_otp(request.via, request.email, request.phone, request.intent, request.name)


@router.post("/auth/forgot", response_model=OtpSendResponse)
async def auth_forgot(request: ForgotRequest):
    """Forgot password — sends a reset OTP to the given identity."""
    return await _send_otp(request.via, request.email, request.phone, "reset", None)


@router.post("/auth/otp/verify", response_model=OtpVerifySuccessOut)
async def auth_otp_verify(request: OtpVerifyRequest):
    channel, target = _resolve_target(request.via, request.email, request.phone)
    if not request.otp:
        raise HTTPException(400, "OTP is required.")

    ok = await store.consume_otp(channel, target, request.intent, request.otp.strip())
    if not ok:
        raise HTTPException(400, "Invalid or expired code. Request a new one.")

    if request.intent == "reset":
        return {"ok": True, "intent": "reset", "reset_token": target}
    if request.intent == "signup":
        if channel == "email":
            user = await store.get_user_by_email(target)
        else:
            user = await store.get_user_by_phone(target)
        if user:
            raise HTTPException(409, "An account already exists for this identity.")
        user = await store.create_user(
            name=request.name or "Researcher",
            email=target if channel == "email" else None,
            phone=target if channel == "phone" else None,
            email_verified=channel == "email",
            phone_verified=channel == "phone",
        )
        token = await store.create_session(user.id)
        return {"ok": True, "intent": "signup", "user": user_to_out(user), "token": token}

    # login
    user = (
        await store.get_user_by_email(target)
        if channel == "email"
        else await store.get_user_by_phone(target)
    )
    if not user:
        raise HTTPException(404, "No account found for this identity.")
    token = await store.create_session(user.id)
    return {"ok": True, "intent": "login", "user": user_to_out(user), "token": token}


@router.post("/auth/register", response_model=AuthResponse)
async def auth_register(request: RegisterRequest):
    email = store.normalize_email(request.email)
    phone = store.normalize_phone(request.phone)
    if not email and not phone:
        raise HTTPException(400, "Provide an email or a phone number.")
    if not request.password or len(request.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    if email and await store.get_user_by_email(email):
        raise HTTPException(409, "An account with this email already exists.")
    if phone and await store.get_user_by_phone(phone):
        raise HTTPException(409, "An account with this phone already exists.")
    user = await store.create_user(
        name=request.name,
        email=email,
        phone=phone,
        password=request.password,
        email_verified=bool(email),
        phone_verified=bool(phone),
    )
    token = await store.create_session(user.id)
    return {"user": user_to_out(user), "token": token}


@router.post("/auth/login", response_model=AuthResponse)
async def auth_login(request: LoginRequest):
    user = None
    if request.email:
        user = await store.get_user_by_email(request.email)
    elif request.phone:
        user = await store.get_user_by_phone(request.phone)
    if not user:
        raise HTTPException(404, "No account found for this identity.")
    if not user.password_hash or not verify_password(request.password, user.password_hash):
        raise HTTPException(401, "Incorrect password.")
    if not user.is_active:
        raise HTTPException(403, "This account is disabled.")
    token = await store.create_session(user.id)
    return {"user": user_to_out(user), "token": token}


@router.post("/auth/reset", response_model=AuthResponse)
async def auth_reset(request: ResetRequest, reset_token: str | None = None):
    channel, target = _resolve_target(request.via, request.email, request.phone)
    if len(request.new_password) < 6:
        raise HTTPException(400, "New password must be at least 6 characters.")
    # Reset requires the OTP in the same call (and checks login/reset codes).
    ok = await store.consume_otp(channel, target, "reset", request.otp.strip())
    if not ok:
        raise HTTPException(400, "Invalid or expired reset code.")
    user = (
        await store.get_user_by_email(target)
        if channel == "email"
        else await store.get_user_by_phone(target)
    )
    if not user:
        raise HTTPException(404, "No account found for this identity.")
    user = await store.set_password(user, request.new_password)
    token = await store.create_session(user.id)
    return {"user": user_to_out(user), "token": token}


def user_to_out(user: User) -> AuthUserOut:
    return AuthUserOut(**store.user_to_out(user))


async def get_current_user(authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    user = await store.get_user_by_session(token)
    if not user:
        raise HTTPException(401, "Session invalid or expired.")
    return user


@router.get("/auth/me", response_model=AuthUserOut)
async def auth_me(user: User = Depends(get_current_user)):
    return user_to_out(user)


@router.post("/auth/logout")
async def auth_logout(
    authorization: str | None = Header(default=None),
    user: User = Depends(get_current_user),
):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        await store.revoke_session(token)
    return {"ok": True}