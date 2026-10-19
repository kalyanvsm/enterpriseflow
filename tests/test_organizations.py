from uuid import uuid4

from fastapi.testclient import TestClient


def test_create_organization(client: TestClient) -> None:
    response = client.post(
        "/api/v1/organizations",
        json={"name": "Acme Corporation"},
    )

    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Acme Corporation"
    assert "id" in data
    assert "created_at" in data


def test_get_existing_organization(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Example Organization"},
    )
    assert create_response.status_code == 201
    organization_id = create_response.json()["id"]

    user_response = client.post(
        "/api/v1/users",
        json={
            "organization_id": organization_id,
            "email": "org-reader@example.com",
            "password": "StrongPassword1234567890!",
        },
    )
    assert user_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "org-reader@example.com",
            "password": "StrongPassword1234567890!",
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]


    response = client.get(
        f"/api/v1/organizations/{organization_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == organization_id


def test_get_missing_organization_returns_404(
        client: TestClient
) -> None:
    create_response = client.post(
        "/api/v1/organizations",
        json={"name": "Existing Organization"},
    )
    assert create_response.status_code == 201
    organization_id = create_response.json()["id"]

    user_response = client.post(
        "/api/v1/users",
        json={
            "organization_id": organization_id,
            "email": "org-reader@example.com",
            "password": "StrongPassword1234567890!",
        },
    )
    assert user_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "org-reader@example.com",
            "password": "StrongPassword1234567890!",
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    response = client.get(
        f"/api/v1/organizations/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_create_organization_rejects_too_short_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/organizations",
        json={"name": "A"},
    )

    assert response.status_code == 422


def test_create_organization_rejects_missing_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/organizations",
        json={},
    )

    assert response.status_code == 422
