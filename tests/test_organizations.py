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
    organization_id = create_response.json()["id"]

    response = client.get(f"/api/v1/organizations/{organization_id}")

    assert response.status_code == 200
    assert response.json()["id"] == organization_id
    assert response.json()["name"] == "Example Organization"


def test_get_missing_organization_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/organizations/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found"


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
