import logging
from typing import Any

import aio_pika
import orjson
from aio_pika import DeliveryMode, ExchangeType, Message, RobustChannel, RobustConnection

from app.core.config import settings

logger = logging.getLogger(__name__)

CLICK_TRACK_QUEUE = "click.track"
LINK_ENRICH_QUEUE = "link.enrich"
EVENT_EXCHANGE = "url_shortener.events"


async def ensure_topology(channel: RobustChannel) -> None:
    exchange = await channel.declare_exchange(EVENT_EXCHANGE, ExchangeType.DIRECT, durable=True)

    click_queue = await channel.declare_queue(CLICK_TRACK_QUEUE, durable=True)
    enrich_queue = await channel.declare_queue(LINK_ENRICH_QUEUE, durable=True)

    await click_queue.bind(exchange, routing_key=CLICK_TRACK_QUEUE)
    await enrich_queue.bind(exchange, routing_key=LINK_ENRICH_QUEUE)


class RabbitMQPublisher:
    def __init__(self, url: str) -> None:
        self.url = url
        self.connection: RobustConnection | None = None
        self.channel: RobustChannel | None = None

    def is_available(self) -> bool:
        if self.connection is None or self.channel is None:
            return False
        if self.connection.is_closed or self.channel.is_closed:
            return False

        connected = getattr(self.connection, "connected", None)
        if connected is not None and not connected.is_set():
            return False
        return True

    async def connect(self) -> None:
        if self.is_available():
            return

        if self.connection and not self.connection.is_closed:
            await self.connection.close()

        self.connection = await aio_pika.connect_robust(self.url)
        self.channel = await self.connection.channel(publisher_confirms=False)
        await ensure_topology(self.channel)

    async def close(self) -> None:
        if self.connection and not self.connection.is_closed:
            await self.connection.close()

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        if not self.is_available():
            await self.connect()

        assert self.channel is not None
        exchange = await self.channel.get_exchange(EVENT_EXCHANGE)
        await exchange.publish(
            Message(
                body=orjson.dumps(payload),
                content_type="application/json",
                delivery_mode=DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )

    async def safe_publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        try:
            await self.publish(routing_key, payload)
        except Exception:
            logger.exception("failed to publish event to RabbitMQ", extra={"routing_key": routing_key})
