from fastapi.testclient import TestClient


def test_admin_endpoint_requires_authentication(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/users/admin-check")

    assert response.status_code == 401


def test_employee_cannot_access_admin_endpoint(
    client: TestClient,
    create_test_user,
) -> None:
    employee = create_test_user(role="employee")

    response = client.get(
        "/api/v1/users/admin-check",
        headers={"Authorization": f"Bearer {employee['token']}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


def test_admin_can_access_admin_endpoint(
    client: TestClient,
    create_test_user,
) -> None:
    admin = create_test_user(role="admin")

    response = client.get(
        "/api/v1/users/admin-check",
        headers={"Authorization": f"Bearer {admin['token']}"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Admin access granted"}
