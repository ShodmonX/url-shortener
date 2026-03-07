import jwt
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.helpers import get_refresh_token_cookie, register_user


def test_register_and_login(client: TestClient) -> None:
    register_payload = register_user(client, "owner@example.com")
    assert register_payload["user"]["email"] == "owner@example.com"
    assert register_payload["access_token"]
    assert register_payload["refresh_token"] is None
    initial_refresh_cookie = get_refresh_token_cookie(client)

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "StrongPass123!"},
    )
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["user"]["email"] == "owner@example.com"
    assert login_payload["access_token"]
    assert login_payload["refresh_token"] is None
    assert get_refresh_token_cookie(client) != initial_refresh_cookie


def test_refresh_token_rotation_and_logout(client: TestClient) -> None:
    register_user(client, "refresh@example.com")
    old_refresh_token = get_refresh_token_cookie(client)

    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200
    refreshed_payload = refresh_response.json()
    assert refreshed_payload["refresh_token"] is None
    new_refresh_token = get_refresh_token_cookie(client)
    assert new_refresh_token != old_refresh_token

    client.cookies.clear()
    reused_refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert reused_refresh_response.status_code == 401
    client.cookies.set(
        settings.refresh_cookie_name,
        new_refresh_token,
        path=settings.refresh_cookie_path,
    )

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204
    assert "Max-Age=0" in (logout_response.headers.get("set-cookie") or "")
    client.cookies.clear()

    post_logout_refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_token},
    )
    assert post_logout_refresh.status_code == 401


def test_refresh_token_body_fallback_still_works(client: TestClient) -> None:
    register_user(client, "body-fallback@example.com")
    old_refresh_token = get_refresh_token_cookie(client)
    client.cookies.clear()

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert refresh_response.status_code == 200
    assert refresh_response.json()["refresh_token"] is None
    assert get_refresh_token_cookie(client) != old_refresh_token


def test_expired_access_token_is_rejected(client: TestClient) -> None:
    auth_payload = register_user(client, "expired@example.com")
    valid_access_token = auth_payload["access_token"]
    current_claims = jwt.decode(
        valid_access_token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"verify_exp": False},
    )
    expired_token = jwt.encode(
        {
            **current_claims,
            "iat": 1,
            "exp": 1,
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
