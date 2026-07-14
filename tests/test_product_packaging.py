"""Ürün paketleme CRUD endpoint testleri."""

from fastapi.testclient import TestClient


def create_product(db_client: TestClient, sku: str) -> int:
    response = db_client.post(
        "/products",
        json={
            "sku": sku,
            "name": "Paketleme Test Urunu",
            "unit_weight_kg": 0.5,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_carton_type(db_client: TestClient, code: str) -> int:
    response = db_client.post(
        "/carton-types",
        json={
            "code": code,
            "name": "Paketleme Test Kolisi",
            "inner_length_cm": 40,
            "inner_width_cm": 30,
            "inner_height_cm": 25,
            "max_weight_kg": 20,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_create_product_packaging(db_client: TestClient) -> None:
    product_id = create_product(db_client, "TEST-PKG-PRODUCT-001")
    carton_type_id = create_carton_type(db_client, "TEST-PKG-CT-001")

    response = db_client.post(
        "/product-packaging",
        json={
            "product_id": product_id,
            "carton_type_id": carton_type_id,
            "units_per_carton": 24,
            "is_default": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["product_id"] == product_id
    assert body["carton_type_id"] == carton_type_id
    assert body["units_per_carton"] == 24
    assert body["is_default"] is True


def test_create_packaging_rejects_missing_reference(db_client: TestClient) -> None:
    response = db_client.post(
        "/product-packaging",
        json={
            "product_id": 999999999,
            "carton_type_id": 999999999,
            "units_per_carton": 12,
            "is_default": False,
        },
    )

    assert response.status_code == 404


def test_create_packaging_rejects_duplicate_combination(db_client: TestClient) -> None:
    product_id = create_product(db_client, "TEST-PKG-PRODUCT-002")
    carton_type_id = create_carton_type(db_client, "TEST-PKG-CT-002")
    payload = {
        "product_id": product_id,
        "carton_type_id": carton_type_id,
        "units_per_carton": 12,
        "is_default": False,
    }

    first_response = db_client.post("/product-packaging", json=payload)
    duplicate_response = db_client.post("/product-packaging", json=payload)

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409


def test_only_one_default_packaging_per_product(db_client: TestClient) -> None:
    product_id = create_product(db_client, "TEST-PKG-PRODUCT-003")
    first_carton_type_id = create_carton_type(db_client, "TEST-PKG-CT-003-A")
    second_carton_type_id = create_carton_type(db_client, "TEST-PKG-CT-003-B")

    first_response = db_client.post(
        "/product-packaging",
        json={
            "product_id": product_id,
            "carton_type_id": first_carton_type_id,
            "units_per_carton": 12,
            "is_default": True,
        },
    )
    second_response = db_client.post(
        "/product-packaging",
        json={
            "product_id": product_id,
            "carton_type_id": second_carton_type_id,
            "units_per_carton": 24,
            "is_default": True,
        },
    )
    list_response = db_client.get(
        "/product-packaging",
        params={"product_id": product_id},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert list_response.status_code == 200
    packaging_options = list_response.json()
    assert len(packaging_options) == 2
    default_options = [item for item in packaging_options if item["is_default"]]
    assert len(default_options) == 1
    assert default_options[0]["id"] == second_response.json()["id"]


def test_product_packaging_lifecycle(db_client: TestClient) -> None:
    product_id = create_product(db_client, "TEST-PKG-PRODUCT-004")
    carton_type_id = create_carton_type(db_client, "TEST-PKG-CT-004")
    create_response = db_client.post(
        "/product-packaging",
        json={
            "product_id": product_id,
            "carton_type_id": carton_type_id,
            "units_per_carton": 10,
            "is_default": False,
        },
    )
    assert create_response.status_code == 201
    packaging_id = create_response.json()["id"]

    get_response = db_client.get(f"/product-packaging/{packaging_id}")
    update_response = db_client.patch(
        f"/product-packaging/{packaging_id}",
        json={"units_per_carton": 20, "is_default": True},
    )
    delete_response = db_client.delete(f"/product-packaging/{packaging_id}")
    final_get_response = db_client.get(f"/product-packaging/{packaging_id}")

    assert get_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["units_per_carton"] == 20
    assert update_response.json()["is_default"] is True
    assert delete_response.status_code == 204
    assert final_get_response.status_code == 404
