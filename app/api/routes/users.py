from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.auth import UserResponse
from app.schemas.user import MyUrlsResponse, OwnedLinkSummary, PaginationMeta
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=current_user.public_id, email=current_user.email, created_at=current_user.created_at)


@router.get("/me/urls", response_model=MyUrlsResponse)
async def get_my_urls(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyUrlsResponse:
    service = UserService(db)
    items, total = await service.list_owned_links(user_id=current_user.id, page=page, page_size=page_size)
    return MyUrlsResponse(
        items=[
            OwnedLinkSummary(
                id=link.public_id,
                original_url=link.long_url,
                short_code=link.short_code,
                created_at=link.created_at,
                expires_at=link.expires_at,
                total_clicks=link.click_count,
            )
            for link in items
        ],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            has_next=(page * page_size) < total,
        ),
    )
