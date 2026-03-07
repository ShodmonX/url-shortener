from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_local_cache, get_redis, rate_limit
from app.cache.redis import LocalTTLCache
from app.core.config import settings
from app.db.session import get_db
from app.services.exceptions import LinkExpiredError, LinkNotFoundError
from app.services.redirect_service import RedirectService
from app.utils.request import get_client_ip, get_country_code

router = APIRouter(tags=["redirects"])


@router.get(
    "/{short_code}",
    dependencies=[Depends(rate_limit("redirect", settings.rate_limit_redirect_per_window))],
)
async def redirect_to_target(
    short_code: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    local_cache: LocalTTLCache = Depends(get_local_cache),
) -> RedirectResponse:
    publisher = getattr(request.app.state, "publisher", None)
    service = RedirectService(db=db, redis=redis, local_cache=local_cache, publisher=publisher)

    try:
        resolved_link, cache_status = await service.resolve(short_code)
    except LinkExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="link has expired") from exc
    except LinkNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="link not found") from exc

    background_tasks.add_task(
        service.enqueue_click_event,
        resolved_link,
        referer=request.headers.get("referer"),
        user_agent=request.headers.get("user-agent"),
        client_ip=get_client_ip(request),
        country_code=get_country_code(request),
        cache_status=cache_status,
    )
    return RedirectResponse(url=resolved_link["long_url"], status_code=status.HTTP_307_TEMPORARY_REDIRECT)
