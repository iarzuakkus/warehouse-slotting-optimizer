"""Ürün CRUD endpoint testleri."""

from fastapi.testclient import TestClient


def test_create_product(db_client: TestClient) -> None:
    response = db_client.post(
        "/products",
        json={
            "sku": "test-crud-001",
            "name": "Test Urunu",
            "unit_weight_kg": 0.52,
            "is_active": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["sku"] == "TEST-CRUD-001"
    assert body["name"] == "Test Urunu"
    assert body["unit_weight_kg"] == "0.520"
    assert body["is_active"] is True


def test_create_product_rejects_duplicate_sku(db_client: TestClient) -> None:
    product_data = {
        "sku": "test-duplicate-001",
        "name": "Ilk Urun",
        "unit_weight_kg": 1.25,
        "is_active": True,
    }
    first_response = db_client.post("/products", json=product_data)

    product_data["sku"] = "TEST-DUPLICATE-001"
    product_data["name"] = "Ikinci Urun"
    duplicate_response = db_client.post("/products", json=product_data)

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {
        "detail": "SKU TEST-DUPLICATE-001 already exists"
    }


def test_product_read_update_and_deactivate_lifecycle(db_client: TestClient) -> None:
    create_response = db_client.post(
        "/products",
        json={
            "sku": "TEST-LIFECYCLE-001",
            "name": "Ilk Ad",
            "unit_weight_kg": 2.5,
            "is_active": True,
        },
    )
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    get_response = db_client.get(f"/products/{product_id}")
    list_response = db_client.get("/products")
    update_response = db_client.patch(
        f"/products/{product_id}",
        json={"name": "Guncel Ad"},
    )
    deactivate_response = db_client.delete(f"/products/{product_id}")
    final_get_response = db_client.get(f"/products/{product_id}")

    assert get_response.status_code == 200
    assert get_response.json()["sku"] == "TEST-LIFECYCLE-001"
    assert list_response.status_code == 200
    assert any(item["id"] == product_id for item in list_response.json())
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Guncel Ad"
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False
    assert final_get_response.status_code == 200
    assert final_get_response.json()["is_active"] is False


def test_update_product_rejects_null_name(db_client: TestClient) -> None:
    create_response = db_client.post(
        "/products",
        json={
            "sku": "TEST-NULL-NAME-001",
            "name": "Gecerli Ad",
            "unit_weight_kg": 1.0,
            "is_active": True,
        },
    )
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    response = db_client.patch(
        f"/products/{product_id}",
        json={"name": None},
    )

    assert response.status_code == 422
