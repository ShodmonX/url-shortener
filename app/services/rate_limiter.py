import math
from time import time

from redis.asyncio import Redis

from app.cache.keys import rate_limit_key
from app.core.config import settings
from app.services.exceptions import RateLimitExceededError


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def enforce(self, scope: str, subject: str, limit: int) -> None:
        now = int(time())
        window_seconds = settings.rate_limit_window_seconds
        bucket = math.floor(now / window_seconds)
        key = rate_limit_key(scope, subject, bucket)

        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, window_seconds)

        if current > limit:
            retry_after = max(await self.redis.ttl(key), 1)
            raise RateLimitExceededError(retry_after)
