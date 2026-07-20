"""Koli tipi CRUD endpoint testleri."""

from fastapi.testclient import TestClient

from tests.factories import carton_type_dimensions


def carton_type_payload(code: str, name: str = "Test Kolisi") -> dict[str, object]:
    return {
        "code": code,
        "name": name,
        **carton_type_dimensions(),
        "max_weight_kg": 20,
        "is_active": True,
    }


def test_create_carton_type(db_client: TestClient) -> None:
    response = db_client.post(
        "/carton-types",
        json=carton_type_payload("test-ct-001"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["code"] == "TEST-CT-001"
    assert body["inner_length_cm"] == "40.00"
    assert body["outer_length_cm"] == "42.00"
    assert body["outer_width_cm"] == "32.00"
    assert body["outer_height_cm"] == "27.00"
    assert body["max_weight_kg"] == "20.000"


def test_create_carton_type_rejects_duplicate_code(db_client: TestClient) -> None:
    first_response = db_client.post(
        "/carton-types",
        json=carton_type_payload("test-ct-duplicate"),
    )
    duplicate_response = db_client.post(
        "/carton-types",
        json=carton_type_payload("TEST-CT-DUPLICATE", "Ikinci Koli"),
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409


def test_carton_type_lifecycle(db_client: TestClient) -> None:
    create_response = db_client.post(
        "/carton-types",
        json=carton_type_payload("TEST-CT-LIFECYCLE", "Ilk Ad"),
    )
    assert create_response.status_code == 201
    carton_type_id = create_response.json()["id"]

    get_response = db_client.get(f"/carton-types/{carton_type_id}")
    list_response = db_client.get("/carton-types")
    update_response = db_client.patch(
        f"/carton-types/{carton_type_id}",
        json={"name": "Guncel Ad", "max_weight_kg": 25},
    )
    deactivate_response = db_client.delete(f"/carton-types/{carton_type_id}")

    assert get_response.status_code == 200
    assert get_response.json()["code"] == "TEST-CT-LIFECYCLE"
    assert list_response.status_code == 200
    assert any(item["id"] == carton_type_id for item in list_response.json())
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Guncel Ad"
    assert update_response.json()["max_weight_kg"] == "25.000"
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False


def test_update_carton_type_rejects_null_dimension(db_client: TestClient) -> None:
    create_response = db_client.post(
        "/carton-types",
        json=carton_type_payload("TEST-CT-NULL"),
    )
    assert create_response.status_code == 201
    carton_type_id = create_response.json()["id"]

    response = db_client.patch(
        f"/carton-types/{carton_type_id}",
        json={"inner_length_cm": None},
    )

    assert response.status_code == 422


def test_create_carton_type_rejects_outer_dimension_smaller_than_inner(
    db_client: TestClient,
) -> None:
    payload = carton_type_payload("TEST-CT-INVALID-OUTER")
    payload["outer_length_cm"] = "39.00"

    response = db_client.post("/carton-types", json=payload)

    assert response.status_code == 422
    assert "outer_length_cm cannot be smaller than inner_length_cm" in str(
        response.json()
    )


def test_update_carton_type_rejects_incompatible_inner_dimension(
    db_client: TestClient,
) -> None:
    create_response = db_client.post(
        "/carton-types",
        json=carton_type_payload("TEST-CT-INVALID-UPDATE"),
    )
    assert create_response.status_code == 201
    carton_type_id = create_response.json()["id"]

    response = db_client.patch(
        f"/carton-types/{carton_type_id}",
        json={"inner_length_cm": "43.00"},
    )

    assert response.status_code == 422
    assert "outer_length_cm cannot be smaller than inner_length_cm" in str(
        response.json()
    )
