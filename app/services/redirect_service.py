from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import orjson
from redis.asyncio import Redis
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.keys import link_cache_key, link_negative_cache_key
from app.cache.redis import LocalTTLCache
from app.core.config import settings
from app.core.security import hash_client_ip
from app.messaging.jobs import publish_or_fallback
from app.messaging.rabbitmq import CLICK_TRACK_QUEUE, RabbitMQPublisher
from app.models import Link
from app.services.exceptions import LinkExpiredError, LinkNotFoundError
from app.services.link_service import normalize_datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


class RedirectService:
    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        local_cache: LocalTTLCache,
        publisher: RabbitMQPublisher | None = None,
    ) -> None:
        self.db = db
        self.redis = redis
        self.local_cache = local_cache
        self.publisher = publisher

    def _ttl_for_payload(self, payload: dict[str, Any]) -> int:
        expires_at_raw = payload.get("expires_at")
        if not expires_at_raw:
            return settings.redirect_cache_ttl_seconds

        expires_at = datetime.fromisoformat(expires_at_raw)
        remaining = int((expires_at - utcnow()).total_seconds())
        return max(remaining, 1)

    async def _validate_cached_payload(self, short_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        expires_at_raw = payload.get("expires_at")
        if not expires_at_raw:
            return payload

        expires_at = datetime.fromisoformat(expires_at_raw)
        if expires_at > utcnow():
            return payload

        cache_key = link_cache_key(short_code)
        await self.redis.delete(cache_key)
        self.local_cache.delete(cache_key)
        raise LinkExpiredError(short_code)

    async def _read_from_db(self, short_code: str) -> dict[str, Any]:
        statement: Select[tuple[Link]] = select(Link).where(Link.short_code == short_code, Link.is_active.is_(True))
        link = await self.db.scalar(statement)
        if link is None:
            raise LinkNotFoundError(short_code)

        expires_at = normalize_datetime(link.expires_at)
        if expires_at and expires_at <= utcnow():
            raise LinkExpiredError(short_code)

        payload = {
            "id": link.id,
            "short_code": link.short_code,
            "long_url": link.long_url,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
        ttl = self._ttl_for_payload(payload)
        await self.redis.set(link_cache_key(short_code), orjson.dumps(payload), ex=ttl)
        self.local_cache.set(link_cache_key(short_code), payload, ttl)
        return payload

    async def resolve(self, short_code: str) -> tuple[dict[str, Any], str]:
        cache_key = link_cache_key(short_code)
        local_hit = self.local_cache.get(cache_key)
        if local_hit is not None:
            return await self._validate_cached_payload(short_code, local_hit), "local"

        if await self.redis.exists(link_negative_cache_key(short_code)):
            raise LinkNotFoundError(short_code)

        redis_hit = await self.redis.get(cache_key)
        if redis_hit is not None:
            payload = orjson.loads(redis_hit)
            payload = await self._validate_cached_payload(short_code, payload)
            self.local_cache.set(cache_key, payload, self._ttl_for_payload(payload))
            return payload, "redis"

        try:
            return await self._read_from_db(short_code), "db"
        except LinkNotFoundError:
            await self.redis.set(link_negative_cache_key(short_code), "1", ex=settings.negative_cache_ttl_seconds)
            raise

    async def enqueue_click_event(
        self,
        resolved_link: dict[str, Any],
        *,
        referer: str | None,
        user_agent: str | None,
        client_ip: str,
        country_code: str | None,
        cache_status: str,
    ) -> None:
        await publish_or_fallback(
            redis=self.redis,
            publisher=self.publisher,
            queue_name=CLICK_TRACK_QUEUE,
            payload={
                "event_id": str(uuid4()),
                "link_id": resolved_link["id"],
                "short_code": resolved_link["short_code"],
                "occurred_at": utcnow().isoformat(),
                "referer": referer,
                "user_agent": user_agent,
                "client_ip_hash": hash_client_ip(client_ip),
                "country_code": country_code,
                "cache_status": cache_status,
            },
        )
