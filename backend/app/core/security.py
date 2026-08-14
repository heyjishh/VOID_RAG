"""Password hashing + opaque token generation for JurAI auth.

Deliberately dependency-free: password hashing uses the stdlib PBKDF2-HMAC
(Python's ``hashlib``), and session/reset tokens are random opaque hex from
:mod:`secrets` stored server-side (no client-readable JWT — revocable and
non-forgeable by construction).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt, expected = encoded.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
    )
    return hmac.compare_digest(digest.hex(), expected)


def new_token(bytes_: int = 32) -> str:
    """Cryptographically random opaque token (64 hex chars)."""
    return secrets.token_hex(bytes_)


def new_otp(length: int = 6) -> str:
    """6-digit numeric OTP — random-start to dodge short-prefix bias."""
    return f"{secrets.randbelow(10**length):0{length}d}"