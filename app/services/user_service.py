from uuid import UUID

from sqlalchemy import Select, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClickEvent, Link
from app.schemas.user import DimensionCount
from app.services.exceptions import LinkNotFoundError


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_owned_links(self, *, user_id: int, page: int, page_size: int) -> tuple[list[Link], int]:
        offset = (page - 1) * page_size
        total_stmt = select(func.count()).select_from(Link).where(Link.user_id == user_id)
        items_stmt: Select[tuple[Link]] = (
            select(Link)
            .where(Link.user_id == user_id)
            .order_by(desc(Link.created_at))
            .offset(offset)
            .limit(page_size)
        )
        total = int(await self.db.scalar(total_stmt) or 0)
        items = list((await self.db.scalars(items_stmt)).all())
        return items, total

    async def get_owned_link(self, *, user_id: int, link_public_id: UUID) -> Link:
        statement: Select[tuple[Link]] = select(Link).where(
            Link.public_id == link_public_id,
            Link.user_id == user_id,
        )
        link = await self.db.scalar(statement)
        if link is None:
            raise LinkNotFoundError(str(link_public_id))
        return link

    async def get_dimension_counts(
        self,
        *,
        link_id: int,
        column,
        limit: int = 5,
    ) -> list[DimensionCount]:
        count_expression = func.count(ClickEvent.id)
        statement = (
            select(column.label("value"), count_expression.label("count"))
            .where(ClickEvent.link_id == link_id, column.is_not(None))
            .group_by(column)
            .order_by(desc(count_expression))
            .limit(limit)
        )
        rows = (await self.db.execute(statement)).all()
        return [DimensionCount(value=str(row.value), count=int(row.count)) for row in rows if row.value]
