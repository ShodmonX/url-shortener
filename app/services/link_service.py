import logging
import random
import re
from datetime import UTC, datetime

import orjson
from redis.asyncio import Redis
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.keys import link_cache_key, link_negative_cache_key
from app.core.config import settings
from app.core.security import generate_manage_token, generate_public_short_code, hash_manage_token, verify_manage_token
from app.messaging.jobs import publish_or_fallback
from app.messaging.rabbitmq import LINK_ENRICH_QUEUE, RabbitMQPublisher
from app.models import Link, User
from app.schemas.link import CreateLinkRequest
from app.services.exceptions import AliasUnavailableError, LinkNotFoundError
from app.utils.url import normalize_target_url

logger = logging.getLogger(__name__)

ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,32}$")


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class LinkService:
    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        publisher: RabbitMQPublisher | None = None,
    ) -> None:
        self.db = db
        self.redis = redis
        self.publisher = publisher

    def _cache_ttl_for_link(self, expires_at: datetime | None) -> int:
        base_ttl = settings.redirect_cache_ttl_seconds + random.randint(0, settings.cache_ttl_jitter_seconds)
        if expires_at is None:
            return base_ttl

        remaining = int((expires_at - utcnow()).total_seconds())
        return max(min(base_ttl, remaining), 1)

    async def _cache_link(self, link: Link) -> None:
        payload = {
            "id": link.id,
            "short_code": link.short_code,
            "long_url": link.long_url,
            "is_active": link.is_active,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        }
        await self.redis.set(
            link_cache_key(link.short_code),
            orjson.dumps(payload),
            ex=self._cache_ttl_for_link(link.expires_at),
        )
        await self.redis.delete(link_negative_cache_key(link.short_code))

    async def _fetch_link(self, short_code: str) -> Link:
        statement: Select[tuple[Link]] = select(Link).where(Link.short_code == short_code)
        link = await self.db.scalar(statement)
        if link is None:
            raise LinkNotFoundError(short_code)
        return link

    def _validate_custom_alias(self, alias: str) -> str:
        normalized = alias.strip()
        if not ALIAS_PATTERN.fullmatch(normalized):
            raise ValueError("custom alias must contain only letters, numbers, hyphen, or underscore")
        if normalized.lower() in settings.reserved_aliases_set:
            raise ValueError("custom alias is reserved")
        return normalized

    async def check_alias_availability(self, alias: str) -> tuple[str, bool, str | None]:
        normalized = alias.strip()
        try:
            normalized = self._validate_custom_alias(normalized)
        except ValueError as exc:
            reason = "reserved" if "reserved" in str(exc).lower() else "invalid"
            return normalized, False, reason

        existing_link_id = await self.db.scalar(select(Link.id).where(Link.short_code == normalized).limit(1))
        if existing_link_id is not None:
            return normalized, False, "already_in_use"

        return normalized, True, None

    async def create_link(self, payload: CreateLinkRequest, owner: User | None = None) -> tuple[Link, str]:
        expires_at = normalize_datetime(payload.expires_at)
        if expires_at and expires_at <= utcnow():
            raise ValueError("expires_at must be in the future")

        manage_token = generate_manage_token()
        normalized_url = normalize_target_url(str(payload.url))

        is_custom_alias = payload.custom_alias is not None
        short_code = self._validate_custom_alias(payload.custom_alias) if payload.custom_alias else ""

        for _ in range(settings.short_code_max_retries):
            link = Link(
                user_id=owner.id if owner is not None else None,
                short_code=short_code or generate_public_short_code(),
                long_url=normalized_url,
                custom_alias=is_custom_alias,
                expires_at=expires_at,
                manage_token_hash=hash_manage_token(manage_token),
            )
            self.db.add(link)

            try:
                await self.db.commit()
                await self.db.refresh(link)
                await self._cache_link(link)
                return link, manage_token
            except IntegrityError as exc:
                await self.db.rollback()
                if is_custom_alias:
                    raise AliasUnavailableError(payload.custom_alias or "") from exc
                logger.warning("short code collision detected, retrying")

        raise RuntimeError("unable to allocate short code after max retries")

    async def enqueue_metadata_job(self, link: Link) -> None:
        await publish_or_fallback(
            redis=self.redis,
            publisher=self.publisher,
            queue_name=LINK_ENRICH_QUEUE,
            payload={
                "short_code": link.short_code,
                "long_url": link.long_url,
            },
        )

    async def get_managed_link(self, short_code: str, manage_token: str) -> Link:
        link = await self._fetch_link(short_code)
        if not verify_manage_token(manage_token, link.manage_token_hash):
            raise LinkNotFoundError(short_code)
        return link
