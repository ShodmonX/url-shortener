from fastapi.testclient import TestClient

from tests.helpers import create_owned_link, register_user


def test_anonymous_url_creation_does_not_attach_owner(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/links",
        json={"url": "https://example.com/public"},
    )
    assert create_response.status_code == 201
    anonymous_payload = create_response.json()
    assert anonymous_payload["short_code"]

    auth_payload = register_user(client, "viewer@example.com")
    list_response = client.get(
        "/api/v1/users/me/urls",
        headers={"Authorization": f"Bearer {auth_payload['access_token']}"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"] == []


def test_authenticated_url_creation_is_owned_and_listed(client: TestClient) -> None:
    auth_payload = register_user(client, "owner@example.com")
    create_owned_link(client, auth_payload["access_token"], "https://example.com/owned", custom_alias="owned-link")

    list_response = client.get(
        "/api/v1/users/me/urls",
        headers={"Authorization": f"Bearer {auth_payload['access_token']}"},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["items"][0]["short_code"] == "owned-link"
    assert payload["items"][0]["original_url"] == "https://example.com/owned"


def test_my_urls_returns_only_current_users_links(client: TestClient) -> None:
    first_user = register_user(client, "first@example.com")
    second_user = register_user(client, "second@example.com")

    create_owned_link(client, first_user["access_token"], "https://example.com/one", custom_alias="first-one")
    create_owned_link(client, first_user["access_token"], "https://example.com/two", custom_alias="first-two")
    create_owned_link(client, second_user["access_token"], "https://example.com/three", custom_alias="second-one")

    first_user_list = client.get(
        "/api/v1/users/me/urls",
        headers={"Authorization": f"Bearer {first_user['access_token']}"},
    )
    assert first_user_list.status_code == 200
    first_items = first_user_list.json()["items"]
    assert {item["short_code"] for item in first_items} == {"first-one", "first-two"}

    second_user_list = client.get(
        "/api/v1/users/me/urls",
        headers={"Authorization": f"Bearer {second_user['access_token']}"},
    )
    assert second_user_list.status_code == 200
    second_items = second_user_list.json()["items"]
    assert [item["short_code"] for item in second_items] == ["second-one"]


def test_stats_endpoint_refuses_non_owners(client: TestClient) -> None:
    owner = register_user(client, "stats-owner@example.com")
    intruder = register_user(client, "intruder@example.com")

    create_owned_link(client, owner["access_token"], "https://example.com/stats", custom_alias="stats-link")
    owner_links_response = client.get(
        "/api/v1/users/me/urls",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    url_id = owner_links_response.json()["items"][0]["id"]

    owner_stats_response = client.get(
        f"/api/v1/urls/{url_id}/stats",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert owner_stats_response.status_code == 200
    owner_stats_payload = owner_stats_response.json()
    assert owner_stats_payload["short_code"] == "stats-link"

    intruder_stats_response = client.get(
        f"/api/v1/urls/{url_id}/stats",
        headers={"Authorization": f"Bearer {intruder['access_token']}"},
    )
    assert intruder_stats_response.status_code == 404


def test_invalid_manage_token_returns_not_found(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/links",
        json={"url": "https://example.com/manage"},
    )
    assert create_response.status_code == 201
    payload = create_response.json()

    details_response = client.get(
        f"/api/v1/links/{payload['short_code']}",
        headers={"X-Manage-Token": "invalid-token"},
    )
    assert details_response.status_code == 404


def test_alias_availability_endpoint_reports_available_used_and_reserved(client: TestClient) -> None:
    available_response = client.get("/api/v1/links/alias-availability", params={"alias": "open-slot"})
    assert available_response.status_code == 200
    assert available_response.json() == {
        "alias": "open-slot",
        "available": True,
        "reason": None,
    }

    create_response = client.post(
        "/api/v1/links",
        json={"url": "https://example.com/claimed", "custom_alias": "claimed-slot"},
    )
    assert create_response.status_code == 201

    used_response = client.get("/api/v1/links/alias-availability", params={"alias": "claimed-slot"})
    assert used_response.status_code == 200
    assert used_response.json() == {
        "alias": "claimed-slot",
        "available": False,
        "reason": "already_in_use",
    }

    reserved_response = client.get("/api/v1/links/alias-availability", params={"alias": "docs"})
    assert reserved_response.status_code == 200
    assert reserved_response.json() == {
        "alias": "docs",
        "available": False,
        "reason": "reserved",
    }
