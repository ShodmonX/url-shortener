from datetime import UTC, datetime

from fastapi import Request, Response

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def get_refresh_token_from_request(request: Request, body_refresh_token: str | None = None) -> str | None:
    if body_refresh_token:
        return body_refresh_token
    return request.cookies.get(settings.refresh_cookie_name)


def set_refresh_token_cookie(response: Response, refresh_token: str, expires_at: datetime) -> None:
    max_age = max(int((expires_at - utcnow()).total_seconds()), 0)
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=max_age,
        expires=expires_at,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def clear_refresh_token_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
    )
