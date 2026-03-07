from collections import OrderedDict
from threading import Lock
from time import monotonic
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings


class LocalTTLCache:
    def __init__(self, max_entries: int) -> None:
        self.max_entries = max_entries
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        now = monotonic()
        with self._lock:
            item = self._entries.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires_at = monotonic() + ttl_seconds
        with self._lock:
            self._entries[key] = (expires_at, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)


def create_redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
