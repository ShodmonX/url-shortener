from collections.abc import Awaitable, Callable

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import LocalTTLCache
from app.db.session import get_db
from app.models import User
from app.services.auth_service import AuthService
from app.services.exceptions import InvalidAccessTokenError, RateLimitExceededError
from app.services.rate_limiter import RedisRateLimiter
from app.utils.request import get_client_ip

bearer_scheme = HTTPBearer(auto_error=False)


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_local_cache(request: Request) -> LocalTTLCache:
    return request.app.state.redirect_local_cache


async def get_manage_token_header(
    x_manage_token: str | None = Header(default=None, alias="X-Manage-Token"),
) -> str:
    if not x_manage_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Manage-Token header is required",
        )
    return x_manage_token


async def get_current_user_optional(
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User | None:
    if credentials is None:
        return None

    service = AuthService(db=db)
    try:
        return await service.authenticate_access_token(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user(
    current_user: User | None = Depends(get_current_user_optional),
) -> User:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def rate_limit(scope: str, limit: int) -> Callable[..., Awaitable[None]]:
    async def dependency(request: Request, redis: Redis = Depends(get_redis)) -> None:
        limiter = RedisRateLimiter(redis)
        subject = get_client_ip(request)
        try:
            await limiter.enforce(scope, subject, limit)
        except RateLimitExceededError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"rate limit exceeded, retry in {exc.retry_after_seconds} seconds",
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc

    return dependency
