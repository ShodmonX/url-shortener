from datetime import UTC, datetime, timedelta

import orjson
import pytest
from fastapi.testclient import TestClient

from app.cache.keys import fallback_queue_key, link_cache_key, link_negative_cache_key
from app.messaging.rabbitmq import CLICK_TRACK_QUEUE


def test_create_manage_and_resolve_through_all_cache_layers(client: TestClient) -> None:
    response = client.post("/api/v1/links", json={"url": "https://example.com/path?q=1"})
    assert response.status_code == 201
    link = response.json()
    code = link["short_code"]
    details = client.get(
        f"/api/v1/links/{code}", headers={"X-Manage-Token": link["manage_token"]}
    )
    assert details.status_code == 200
    assert details.json()["url"] == "https://example.com/path?q=1"
    assert "manage_token" not in details.json()

    redis = client.app.state.redis
    local_cache = client.app.state.redirect_local_cache
    for expected_source in ("redis", "local", "db"):
        if expected_source == "db":
            local_cache.delete(link_cache_key(code))
            client.portal.call(redis.delete, link_cache_key(code))
        redirect = client.get(f"/{code}", follow_redirects=False)
        assert redirect.status_code == 307
        assert redirect.headers["location"] == "https://example.com/path?q=1"
        # Read the real job envelope produced by the redirect background task.
        entry = client.portal.call(redis.blpop, fallback_queue_key(CLICK_TRACK_QUEUE))
        assert entry is not None
        event = orjson.loads(entry[1])["payload"]
        assert event["short_code"] == code
        assert event["cache_status"] == expected_source
        assert event["client_ip_hash"] != "testclient"


def test_creation_clears_cached_miss_and_duplicate_alias_preserves_target(client: TestClient) -> None:
    assert client.get("/new-alias").status_code == 404
    redis = client.app.state.redis
    assert client.portal.call(redis.exists, link_negative_cache_key("new-alias"))
    created = client.post(
        "/api/v1/links",
        json={"url": "https://example.com/original", "custom_alias": "new-alias"},
    )
    assert created.status_code == 201
    assert not client.portal.call(redis.exists, link_negative_cache_key("new-alias"))
    duplicate = client.post(
        "/api/v1/links",
        json={"url": "https://example.com/replacement", "custom_alias": "new-alias"},
    )
    assert duplicate.status_code == 409
    redirect = client.get("/new-alias", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "https://example.com/original"


@pytest.mark.parametrize(
    "payload",
    [
        {"url": "javascript:alert(1)"},
        {"url": "https://example.com", "custom_alias": "docs"},
        {"url": "https://example.com", "custom_alias": "bad!alias"},
        {"url": "https://example.com", "expires_at": "2000-01-01T00:00:00Z"},
    ],
)
def test_invalid_link_requests_are_rejected(client: TestClient, payload: dict) -> None:
    assert client.post("/api/v1/links", json=payload).status_code == 422


def test_generated_code_collision_retries_without_overwriting(client: TestClient, monkeypatch) -> None:
    codes = iter(["collision01", "collision01", "replacement1"])
    monkeypatch.setattr("app.services.link_service.generate_public_short_code", lambda: next(codes))
    for target, expected_code in (("first", "collision01"), ("second", "replacement1")):
        created = client.post("/api/v1/links", json={"url": f"https://example.com/{target}"})
        assert created.status_code == 201
        assert created.json()["short_code"] == expected_code
        redirect = client.get(f"/{expected_code}", follow_redirects=False)
        assert redirect.headers["location"] == f"https://example.com/{target}"


@pytest.mark.parametrize("cache_source", ["local", "redis", "db"])
def test_expired_link_is_gone_from_every_resolution_path(client: TestClient, monkeypatch, cache_source: str) -> None:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=10)
    created = client.post(
        "/api/v1/links", json={"url": "https://example.com/temporary", "expires_at": expires_at.isoformat()}
    )
    assert created.status_code == 201
    code = created.json()["short_code"]
    if cache_source == "local":
        assert client.get(f"/{code}", follow_redirects=False).status_code == 307
    elif cache_source == "db":
        client.portal.call(client.app.state.redis.delete, link_cache_key(code))
    monkeypatch.setattr("app.services.redirect_service.utcnow", lambda: expires_at + timedelta(seconds=1))
    assert client.get(f"/{code}", follow_redirects=False).status_code == 410
