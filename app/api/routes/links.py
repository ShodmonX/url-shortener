from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional, get_manage_token_header, get_redis, rate_limit
from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.schemas.link import (
    AnalyticsPoint,
    AnalyticsResponse,
    AliasAvailabilityResponse,
    CreateLinkRequest,
    LinkDetailsResponse,
    LinkResponse,
    PreviewResponse,
    RecentClickEvent,
)
from app.services.analytics_service import AnalyticsService
from app.services.exceptions import AliasUnavailableError, LinkNotFoundError
from app.services.link_service import LinkService

router = APIRouter(
    prefix="/links",
    tags=["links"],
)


def build_short_url(short_code: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/{short_code}"


@router.post(
    "",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("create", settings.rate_limit_create_per_window))],
)
async def create_link(
    payload: CreateLinkRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    current_user: User | None = Depends(get_current_user_optional),
) -> LinkResponse:
    publisher = getattr(request.app.state, "publisher", None)
    service = LinkService(db=db, redis=redis, publisher=publisher)

    try:
        link, manage_token = await service.create_link(payload, owner=current_user)
    except AliasUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="custom alias is already in use") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    background_tasks.add_task(service.enqueue_metadata_job, link)

    return LinkResponse(
        short_code=link.short_code,
        short_url=build_short_url(link.short_code),
        url=link.long_url,
        custom_alias=link.custom_alias,
        expires_at=link.expires_at,
        metadata_status=link.metadata_status,
        created_at=link.created_at,
        manage_token=manage_token,
    )


@router.get(
    "/alias-availability",
    response_model=AliasAvailabilityResponse,
    dependencies=[Depends(rate_limit("create", settings.rate_limit_create_per_window))],
)
async def check_alias_availability(
    alias: str = Query(..., min_length=4, max_length=32),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AliasAvailabilityResponse:
    service = LinkService(db=db, redis=redis)
    normalized_alias, available, reason = await service.check_alias_availability(alias)
    return AliasAvailabilityResponse(alias=normalized_alias, available=available, reason=reason)


@router.get(
    "/{short_code}",
    response_model=LinkDetailsResponse,
    dependencies=[Depends(rate_limit("manage", settings.rate_limit_manage_per_window))],
)
async def get_link_details(
    short_code: str,
    manage_token: str = Depends(get_manage_token_header),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> LinkDetailsResponse:
    service = LinkService(db=db, redis=redis)
    try:
        link = await service.get_managed_link(short_code, manage_token)
    except LinkNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="link not found") from exc

    return LinkDetailsResponse(
        short_code=link.short_code,
        short_url=build_short_url(link.short_code),
        url=link.long_url,
        expires_at=link.expires_at,
        custom_alias=link.custom_alias,
        click_count=link.click_count,
        last_clicked_at=link.last_clicked_at,
        metadata_status=link.metadata_status,
        preview_metadata=link.preview_metadata,
        has_qr_code=link.qr_svg is not None,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


@router.get(
    "/{short_code}/preview",
    response_model=PreviewResponse,
    dependencies=[Depends(rate_limit("manage", settings.rate_limit_manage_per_window))],
)
async def get_link_preview(
    short_code: str,
    manage_token: str = Depends(get_manage_token_header),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> PreviewResponse:
    service = LinkService(db=db, redis=redis)
    try:
        link = await service.get_managed_link(short_code, manage_token)
    except LinkNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="link not found") from exc

    return PreviewResponse(
        short_code=link.short_code,
        status=link.metadata_status,
        metadata=link.preview_metadata,
        updated_at=link.updated_at,
    )


@router.get(
    "/{short_code}/qr",
    dependencies=[Depends(rate_limit("manage", settings.rate_limit_manage_per_window))],
)
async def get_qr_code(
    short_code: str,
    manage_token: str = Depends(get_manage_token_header),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Response:
    service = LinkService(db=db, redis=redis)
    try:
        link = await service.get_managed_link(short_code, manage_token)
    except LinkNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="link not found") from exc

    if not link.qr_svg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QR code not generated yet")

    return Response(content=link.qr_svg, media_type="image/svg+xml")


@router.get(
    "/{short_code}/analytics",
    response_model=AnalyticsResponse,
    dependencies=[Depends(rate_limit("manage", settings.rate_limit_manage_per_window))],
)
async def get_link_analytics(
    short_code: str,
    manage_token: str = Depends(get_manage_token_header),
    days: int = Query(default=settings.default_analytics_days, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AnalyticsResponse:
    link_service = LinkService(db=db, redis=redis)
    analytics_service = AnalyticsService(db=db)

    try:
        link = await link_service.get_managed_link(short_code, manage_token)
    except LinkNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="link not found") from exc

    stats, recent_events = await analytics_service.get_analytics(link, days)
    return AnalyticsResponse(
        short_code=link.short_code,
        total_clicks=link.click_count,
        last_clicked_at=link.last_clicked_at,
        daily=[
            AnalyticsPoint(date=stat.bucket_date, clicks=stat.clicks, unique_visitors=stat.unique_visitors)
            for stat in stats
        ],
        recent_events=[
            RecentClickEvent(
                occurred_at=event.occurred_at,
                referer=event.referer,
                country_code=event.country_code,
                cache_status=event.cache_status,
            )
            for event in recent_events
        ],
    )
