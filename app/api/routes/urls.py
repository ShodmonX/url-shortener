from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import ClickEvent, User
from app.schemas.link import AnalyticsPoint
from app.schemas.user import UrlStatsResponse
from app.services.analytics_service import AnalyticsService
from app.services.exceptions import LinkNotFoundError
from app.services.user_service import UserService

router = APIRouter(prefix="/urls", tags=["urls"])


@router.get("/{url_id}/stats", response_model=UrlStatsResponse)
async def get_url_stats(
    url_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UrlStatsResponse:
    user_service = UserService(db)
    analytics_service = AnalyticsService(db)

    try:
        link = await user_service.get_owned_link(user_id=current_user.id, link_public_id=url_id)
    except LinkNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="url not found") from exc

    daily_stats, _recent_events = await analytics_service.get_analytics(link, days)
    referrers = await user_service.get_dimension_counts(link_id=link.id, column=ClickEvent.referer)
    countries = await user_service.get_dimension_counts(link_id=link.id, column=ClickEvent.country_code)
    devices = await analytics_service.get_recent_device_placeholders(link.id)

    return UrlStatsResponse(
        id=link.public_id,
        short_code=link.short_code,
        original_url=link.long_url,
        total_clicks=link.click_count,
        created_at=link.created_at,
        expires_at=link.expires_at,
        last_clicked_at=link.last_clicked_at,
        daily_clicks=[
            AnalyticsPoint(date=stat.bucket_date, clicks=stat.clicks, unique_visitors=stat.unique_visitors)
            for stat in daily_stats
        ],
        top_referrers=referrers,
        top_countries=countries,
        top_devices=devices,
    )
