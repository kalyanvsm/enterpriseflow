from fastapi.testclient import TestClient


def create_organization_and_login(
        client: TestClient,
        organization_name: str,
        email: str,
) -> tuple[str, str]:
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": organization_name},
    )
    assert organization_response.status_code == 201
    organization_id = organization_response.json()["id"]

    user_response = client.post(
        "/api/v1/users",
        json={
            "organization_id": organization_id,
            "email": email,
            "password": "StrongPassword1234567890!",
        },
    )
    assert user_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "StrongPassword1234567890!",
        },
    )
    assert login_response.status_code == 200

    return organization_id, login_response.json()["access_token"]

def test_organization_detail_requires_authentication(
        client: TestClient,
) -> None:
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": "Private Organization"},
    )
    organization_id = organization_response.json()["id"]

    response = client.get(f"/api/v1/organizations/{organization_id}")

    assert response.status_code == 401

def test_user_cannot_read_another_organization(
        client: TestClient,
) -> None:
    organization_a_id, token_a = create_organization_and_login(
        client,
        "Organization Alpha",
        "alpha@example.com",
    )
    organization_b_id, _ = create_organization_and_login(
        client,
        "Organization Beta",
        "beta@example.com",
    )

    response = client.get(
        f"/api/v1/organizations/{organization_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert organization_a_id != organization_b_id
    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found"

def test_user_can_read_own_organization(
        client: TestClient,
) -> None:
    organization_id, token = create_organization_and_login(
        client,
        "My Organization",
        "owner@example.com",
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == organization_id
    assert response.json()["name"] == "My Organization"