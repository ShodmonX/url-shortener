import asyncio
import time
from collections import defaultdict
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app


class FakeRedis:
    def __init__(self) -> None:
        self._strings: dict[str, str] = {}
        self._expirations: dict[str, float] = {}
        self._sets: dict[str, set[str]] = defaultdict(set)
        self._lists: dict[str, list[str]] = defaultdict(list)

    def _purge_if_expired(self, key: str) -> None:
        expires_at = self._expirations.get(key)
        if expires_at is not None and expires_at <= time.time():
            self._strings.pop(key, None)
            self._sets.pop(key, None)
            self._lists.pop(key, None)
            self._expirations.pop(key, None)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._strings[key] = value
        if ex is not None:
            self._expirations[key] = time.time() + ex
        else:
            self._expirations.pop(key, None)
        return True

    async def get(self, key: str) -> str | None:
        self._purge_if_expired(key)
        return self._strings.get(key)

    async def delete(self, key: str) -> int:
        deleted = 0
        if key in self._strings:
            deleted += 1
            self._strings.pop(key, None)
        if key in self._sets:
            deleted += 1
            self._sets.pop(key, None)
        if key in self._lists:
            deleted += 1
            self._lists.pop(key, None)
        self._expirations.pop(key, None)
        return deleted

    async def exists(self, key: str) -> int:
        self._purge_if_expired(key)
        return int(key in self._strings or key in self._sets or key in self._lists)

    async def incr(self, key: str) -> int:
        self._purge_if_expired(key)
        current = int(self._strings.get(key, "0"))
        current += 1
        self._strings[key] = str(current)
        return current

    async def expire(self, key: str, seconds: int) -> bool:
        if key in self._strings or key in self._sets:
            self._expirations[key] = time.time() + seconds
            return True
        return False

    async def ttl(self, key: str) -> int:
        self._purge_if_expired(key)
        expires_at = self._expirations.get(key)
        if expires_at is None:
            return -1
        return max(int(expires_at - time.time()), 0)

    async def pfadd(self, key: str, *values: str) -> int:
        self._purge_if_expired(key)
        current = self._sets[key]
        size_before = len(current)
        current.update(values)
        return int(len(current) != size_before)

    async def pfcount(self, key: str) -> int:
        self._purge_if_expired(key)
        return len(self._sets.get(key, set()))

    async def ping(self) -> bool:
        return True

    async def rpush(self, key: str, *values: str) -> int:
        self._purge_if_expired(key)
        self._lists[key].extend(values)
        return len(self._lists[key])

    async def lpush(self, key: str, *values: str) -> int:
        self._purge_if_expired(key)
        for value in reversed(values):
            self._lists[key].insert(0, value)
        return len(self._lists[key])

    async def blpop(self, key: str, timeout: int = 0) -> tuple[str, str] | None:
        self._purge_if_expired(key)
        items = self._lists.get(key)
        if items:
            return key, items.pop(0)
        if timeout > 0:
            await asyncio.sleep(0)
        return None

    async def aclose(self) -> None:
        self._strings.clear()
        self._sets.clear()
        self._lists.clear()
        self._expirations.clear()


async def _create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def _drop_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    fake_redis = FakeRedis()

    async def fail_rabbitmq_connect(self) -> None:
        raise RuntimeError("rabbitmq disabled in tests")

    monkeypatch.setattr("app.main.create_redis_client", lambda: fake_redis)
    monkeypatch.setattr("app.main.RabbitMQPublisher.connect", fail_rabbitmq_connect)

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    asyncio.run(_create_schema(engine))

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    asyncio.run(_drop_schema(engine))
    asyncio.run(engine.dispose())
