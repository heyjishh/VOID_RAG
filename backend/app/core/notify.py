"""OTP delivery channels — real providers when configured, dev fallback else.

Two delivery paths:

* **email** — SMTP via the standard library :mod:`smtplib` (STARTTLS when
  enabled). Configured by SMTP_* settings.
* **sms** — a generic JSON POST to ``SMS_GATEWAY_URL`` (Bearer key in
  ``SMS_GATEWAY_KEY``). Body: ``{"to": ..., "message": ...}``.

When neither provider is wired for a channel (or ``AUTH_DEV_RETURN_OTP``),
delivery falls back to **dev mode**: the OTP is logged and returned so the
whole flow works offline. The router decides what to surface via
:func:`deliver`.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText

import httpx

from app.config.settings import settings

logger = logging.getLogger("juryai.auth")


def channel_status(channel: str) -> str:
    """Real provider if wired, else 'dev' (if dev fallback enabled) or 'unavailable'."""
    providers = settings.auth_provider_status
    if channel == "email" and providers["email"]:
        return "email"
    if channel == "sms" and providers["sms"]:
        return "sms"
    if providers["dev"]:
        return "dev"
    return "unavailable"


def _send_email_sync(to: str, subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.sendmail(settings.SMTP_FROM, [to], msg.as_string())


async def send_email_otp(to: str, otp: str) -> str:
    if channel_status("email") != "email":
        return "dev"
    subject = f"Your {settings.SMS_FROM_NAME} verification code: {otp}"
    body = (
        f"Your {settings.SMS_FROM_NAME} verification code is {otp}.\n"
        f"It expires in {settings.AUTH_OTP_TTL_SECONDS // 60} minutes.\n"
        "If you did not request this, you can safely ignore this email."
    )
    await asyncio.to_thread(_send_email_sync, to, subject, body)
    return "email"


async def send_sms_otp(to: str, otp: str) -> str:
    if channel_status("sms") != "sms":
        return "dev"
    message = (
        f"{settings.SMS_FROM_NAME} OTP: {otp} (valid "
        f"{settings.AUTH_OTP_TTL_SECONDS // 60} min)"
    )
    headers = {"Content-Type": "application/json"}
    if settings.SMS_GATEWAY_KEY:
        headers["Authorization"] = f"Bearer {settings.SMS_GATEWAY_KEY}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            settings.SMS_GATEWAY_URL,
            json={"to": to, "message": message, "from": settings.SMS_FROM_NAME},
            headers=headers,
        )
        resp.raise_for_status()
    return "sms"