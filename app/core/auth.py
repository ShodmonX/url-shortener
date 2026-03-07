import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.config import settings


class TokenDecodeError(Exception):
    pass


class TokenExpiredError(TokenDecodeError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("utf-8"))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=settings.password_scrypt_n,
        r=settings.password_scrypt_r,
        p=settings.password_scrypt_p,
        dklen=64,
    )
    return (
        f"scrypt${settings.password_scrypt_n}${settings.password_scrypt_r}${settings.password_scrypt_p}"
        f"${_b64encode(salt)}${_b64encode(derived_key)}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, n_value, r_value, p_value, salt_encoded, digest_encoded = password_hash.split("$", maxsplit=5)
        salt = _b64decode(salt_encoded)
        expected = _b64decode(digest_encoded)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_value),
            r=int(r_value),
            p=int(p_value),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False

    if scheme != "scrypt":
        return False

    return hmac.compare_digest(actual, expected)


def _encode_token(payload: dict) -> str:
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: int, user_public_id: UUID) -> tuple[str, datetime]:
    expires_at = utcnow() + timedelta(minutes=settings.jwt_access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "uid": str(user_public_id),
        "type": "access",
        "iat": int(utcnow().timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return _encode_token(payload), expires_at


def create_refresh_token(*, user_id: int, user_public_id: UUID, jti: UUID) -> tuple[str, datetime]:
    expires_at = utcnow() + timedelta(days=settings.jwt_refresh_token_ttl_days)
    payload = {
        "sub": str(user_id),
        "uid": str(user_public_id),
        "jti": str(jti),
        "type": "refresh",
        "iat": int(utcnow().timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return _encode_token(payload), expires_at


def generate_refresh_token_id() -> UUID:
    return uuid4()


def decode_token(token: str, *, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("token has expired") from exc
    except InvalidTokenError as exc:
        raise TokenDecodeError("invalid token") from exc

    token_type = payload.get("type")
    if token_type != expected_type:
        raise TokenDecodeError(f"invalid token type: expected {expected_type}")
    return payload
