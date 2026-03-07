from fastapi.testclient import TestClient

from app.core.config import settings


def register_user(client: TestClient, email: str, password: str = "StrongPass123!") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def get_refresh_token_cookie(client: TestClient) -> str:
    refresh_token = client.cookies.get(settings.refresh_cookie_name)
    assert refresh_token is not None
    return refresh_token


def create_owned_link(client: TestClient, access_token: str, url: str, custom_alias: str | None = None) -> dict:
    payload = {"url": url}
    if custom_alias is not None:
        payload["custom_alias"] = custom_alias
    response = client.post(
        "/api/v1/links",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()
