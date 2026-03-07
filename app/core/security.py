import hashlib
import hmac
import secrets

from app.core.config import settings
from app.utils.base62 import generate_short_code


def generate_public_short_code() -> str:
    return generate_short_code(settings.short_code_length)


def generate_manage_token() -> str:
    return secrets.token_urlsafe(settings.manage_token_length)


def hash_manage_token(token: str) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_manage_token(token: str, token_hash: str) -> bool:
    expected = hash_manage_token(token)
    return hmac.compare_digest(expected, token_hash)


def hash_client_ip(client_ip: str) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        client_ip.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
