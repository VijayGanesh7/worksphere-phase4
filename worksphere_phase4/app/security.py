"""Password hashing (stdlib scrypt) and JWT helpers. No web-framework imports here."""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from .config import settings

_ALGO = "HS256"
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGO)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[_ALGO], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None
