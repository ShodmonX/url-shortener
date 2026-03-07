import asyncio
import logging

import aio_pika
import orjson

from app.cache.keys import fallback_queue_key
from app.cache.redis import create_redis_client
from app.core.config import settings
from app.db.session import SessionLocal, close_db_engine
from app.messaging.jobs import requeue_or_dead_letter
from app.messaging.rabbitmq import CLICK_TRACK_QUEUE, LINK_ENRICH_QUEUE, ensure_topology
from app.services.analytics_service import AnalyticsIngestService
from app.services.metadata_service import MetadataEnrichmentService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def handle_click(payload: dict, redis) -> None:
    async with SessionLocal() as session:
        service = AnalyticsIngestService(db=session, redis=redis)
        await service.record_click(payload)


async def handle_enrichment(payload: dict) -> None:
    short_code = payload["short_code"]
    async with SessionLocal() as session:
        service = MetadataEnrichmentService(db=session)
        await service.enrich_link(short_code, settings.public_base_url)


async def process_job(handler, payload: dict, *, name: str, redis, retries: int = 0) -> None:
    try:
        await handler(payload)
        logger.debug("processed %s event", name)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("failed to process %s event", name)
        outcome = await requeue_or_dead_letter(
            redis=redis,
            queue_name=name,
            payload=payload,
            retries=retries,
            error=str(exc),
        )
        logger.warning("moved %s event to %s", name, outcome)


async def consume_queue(queue: aio_pika.abc.AbstractQueue, handler, *, name: str, redis) -> None:
    async with queue.iterator() as iterator:
        async for message in iterator:
            try:
                payload = orjson.loads(message.body)
                await process_job(handler, payload, name=name, redis=redis)
            except asyncio.CancelledError:
                await message.reject(requeue=True)
                raise
            except Exception as exc:
                logger.exception("failed to decode %s event from RabbitMQ", name)
                outcome = await requeue_or_dead_letter(
                    redis=redis,
                    queue_name=name,
                    payload={"raw_message": message.body.decode("utf-8", errors="replace")},
                    retries=settings.background_job_max_retries,
                    error=str(exc),
                )
                logger.warning("moved malformed %s event to %s", name, outcome)
                await message.ack()
            else:
                try:
                    await message.ack()
                except aio_pika.exceptions.MessageProcessError:
                    logger.debug("message for %s was already processed", name)


async def consume_fallback_queue(queue_name: str, handler, *, redis) -> None:
    key = fallback_queue_key(queue_name)
    while True:
        entry = await redis.blpop(key, timeout=settings.fallback_queue_poll_timeout_seconds)
        if entry is None:
            continue

        _queue_key, raw_value = entry
        try:
            payload_envelope = orjson.loads(raw_value)
        except Exception as exc:
            logger.exception("failed to decode %s fallback event", queue_name)
            outcome = await requeue_or_dead_letter(
                redis=redis,
                queue_name=queue_name,
                payload={"raw_message": str(raw_value)},
                retries=settings.background_job_max_retries,
                error=str(exc),
            )
            logger.warning("moved malformed %s fallback event to %s", queue_name, outcome)
            continue
        payload = payload_envelope.get("payload", payload_envelope)
        retries = int(payload_envelope.get("retries", 0))
        await process_job(handler, payload, name=queue_name, redis=redis, retries=retries)


async def consume_rabbit(redis) -> None:
    while True:
        connection = None
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=settings.rabbitmq_prefetch_count)
            await ensure_topology(channel)

            click_queue = await channel.declare_queue(CLICK_TRACK_QUEUE, durable=True)
            enrich_queue = await channel.declare_queue(LINK_ENRICH_QUEUE, durable=True)

            await asyncio.gather(
                consume_queue(click_queue, lambda payload: handle_click(payload, redis), name=CLICK_TRACK_QUEUE, redis=redis),
                consume_queue(enrich_queue, handle_enrichment, name=LINK_ENRICH_QUEUE, redis=redis),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("RabbitMQ consumer loop failed, retrying")
            await asyncio.sleep(5)
        finally:
            if connection is not None and not connection.is_closed:
                await connection.close()


async def main() -> None:
    redis = create_redis_client()

    try:
        await asyncio.gather(
            consume_rabbit(redis),
            consume_fallback_queue(CLICK_TRACK_QUEUE, lambda payload: handle_click(payload, redis), redis=redis),
            consume_fallback_queue(LINK_ENRICH_QUEUE, handle_enrichment, redis=redis),
        )
    finally:
        await redis.aclose()
        await close_db_engine()


if __name__ == "__main__":
    asyncio.run(main())
