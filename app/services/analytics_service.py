import zlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import Select, desc, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.keys import analytics_counter_key, analytics_unique_visitors_key
from app.core.config import settings
from app.models import ClickEvent, Link, LinkDailyStat
from app.schemas.user import DimensionCount


def utcnow() -> datetime:
    return datetime.now(UTC)


class AnalyticsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_analytics(self, link: Link, days: int) -> tuple[list[LinkDailyStat], list[ClickEvent]]:
        start_date = utcnow().date() - timedelta(days=max(days - 1, 0))

        stats_stmt: Select[tuple[LinkDailyStat]] = (
            select(LinkDailyStat)
            .where(LinkDailyStat.link_id == link.id, LinkDailyStat.bucket_date >= start_date)
            .order_by(LinkDailyStat.bucket_date.asc())
        )
        recent_stmt: Select[tuple[ClickEvent]] = (
            select(ClickEvent)
            .where(ClickEvent.link_id == link.id)
            .order_by(desc(ClickEvent.occurred_at))
            .limit(settings.analytics_recent_events_limit)
        )

        stats = list((await self.db.scalars(stats_stmt)).all())
        recent_events = list((await self.db.scalars(recent_stmt)).all())
        return stats, recent_events

    async def get_recent_device_placeholders(self, link_id: int) -> list[DimensionCount]:
        del link_id
        return []


class AnalyticsIngestService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.redis = redis

    async def record_click(self, payload: dict) -> None:
        occurred_at = datetime.fromisoformat(payload["occurred_at"])
        bucket_date = occurred_at.date()
        link_id = int(payload["link_id"])
        client_ip_hash = payload["client_ip_hash"]
        event_id = UUID(payload["event_id"])

        shard = zlib.crc32(client_ip_hash.encode("utf-8")) % settings.click_analytics_shards
        counter_key = analytics_counter_key(link_id, bucket_date, shard)
        unique_visitors_key = analytics_unique_visitors_key(link_id, bucket_date)

        await self.redis.incr(counter_key)
        await self.redis.expire(counter_key, 172800)
        await self.redis.pfadd(unique_visitors_key, client_ip_hash)
        await self.redis.expire(unique_visitors_key, 172800)
        unique_visitors = int(await self.redis.pfcount(unique_visitors_key))

        event_insert = insert(ClickEvent).values(
            request_id=event_id,
            link_id=link_id,
            occurred_at=occurred_at,
            referer=payload.get("referer"),
            user_agent=payload.get("user_agent"),
            client_ip_hash=client_ip_hash,
            country_code=payload.get("country_code"),
            cache_status=payload.get("cache_status", "db"),
        )
        event_insert = event_insert.on_conflict_do_nothing(index_elements=["request_id"]).returning(ClickEvent.id)
        inserted_event_id = await self.db.scalar(event_insert)
        if inserted_event_id is None:
            await self.db.rollback()
            return

        await self.db.execute(
            update(Link)
            .where(Link.id == link_id)
            .values(
                click_count=Link.click_count + 1,
                last_clicked_at=occurred_at,
            )
        )

        upsert = insert(LinkDailyStat).values(
            link_id=link_id,
            bucket_date=bucket_date,
            clicks=1,
            unique_visitors=unique_visitors,
        )
        upsert = upsert.on_conflict_do_update(
            constraint="uq_link_daily_stats_bucket",
            set_={
                "clicks": LinkDailyStat.clicks + 1,
                "unique_visitors": unique_visitors,
                "updated_at": utcnow(),
            },
        )
        await self.db.execute(upsert)
        await self.db.commit()
