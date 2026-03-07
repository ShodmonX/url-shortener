import logging
from datetime import UTC, datetime
from typing import Any

import orjson
from redis.asyncio import Redis

from app.cache.keys import dead_letter_queue_key, fallback_queue_key
from app.core.config import settings
from app.messaging.rabbitmq import RabbitMQPublisher

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _encode_message(payload: dict[str, Any]) -> str:
    return orjson.dumps(payload).decode("utf-8")


def build_retry_envelope(payload: dict[str, Any], *, retries: int = 0) -> dict[str, Any]:
    return {
        "payload": payload,
        "retries": retries,
        "queued_at": utcnow().isoformat(),
    }


async def publish_or_fallback(
    *,
    redis: Redis,
    publisher: RabbitMQPublisher | None,
    queue_name: str,
    payload: dict[str, Any],
) -> str:
    if publisher is not None:
        try:
            await publisher.publish(queue_name, payload)
            return "rabbitmq"
        except Exception:
            logger.exception("failed to publish job, using redis fallback", extra={"queue_name": queue_name})

    await redis.rpush(
        fallback_queue_key(queue_name),
        _encode_message(build_retry_envelope(payload)),
    )
    return "redis-fallback"


async def requeue_or_dead_letter(
    *,
    redis: Redis,
    queue_name: str,
    payload: dict[str, Any],
    retries: int,
    error: str,
) -> str:
    next_retries = retries + 1
    if next_retries > settings.background_job_max_retries:
        await redis.rpush(
            dead_letter_queue_key(queue_name),
            _encode_message(
                {
                    "payload": payload,
                    "retries": retries,
                    "failed_at": utcnow().isoformat(),
                    "error": error,
                }
            ),
        )
        return "dead-letter"

    await redis.rpush(
        fallback_queue_key(queue_name),
        _encode_message(build_retry_envelope(payload, retries=next_retries)),
    )
    return "requeued"
