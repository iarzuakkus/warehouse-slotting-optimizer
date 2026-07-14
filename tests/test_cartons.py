"""Fiziksel koli endpoint testleri."""

from fastapi.testclient import TestClient


def create_carton_dependencies(
    db_client: TestClient,
    suffix: str,
    units_per_carton: int = 24,
) -> tuple[int, int]:
    product_response = db_client.post(
        "/products",
        json={
            "sku": f"TEST-CARTON-PRODUCT-{suffix}",
            "name": "Fiziksel Koli Test Urunu",
            "unit_weight_kg": 0.5,
            "is_active": True,
        },
    )
    assert product_response.status_code == 201

    carton_type_response = db_client.post(
        "/carton-types",
        json={
            "code": f"TEST-CARTON-CT-{suffix}",
            "name": "Fiziksel Koli Test Tipi",
            "inner_length_cm": 40,
            "inner_width_cm": 30,
            "inner_height_cm": 25,
            "max_weight_kg": 20,
            "is_active": True,
        },
    )
    assert carton_type_response.status_code == 201

    packaging_response = db_client.post(
        "/product-packaging",
        json={
            "product_id": product_response.json()["id"],
            "carton_type_id": carton_type_response.json()["id"],
            "units_per_carton": units_per_carton,
            "is_default": True,
        },
    )
    assert packaging_response.status_code == 201

    location_response = db_client.post(
        "/warehouse-locations",
        json={
            "aisle": f"TEST-{suffix}",
            "bay": "01",
            "level": "01",
            "slot": "01",
            "max_weight_kg": 750,
            "distance_from_dispatch_m": 10,
            "is_active": True,
        },
    )
    assert location_response.status_code == 201

    return packaging_response.json()["id"], location_response.json()["id"]


def carton_payload(
    carton_number: str,
    packaging_id: int,
    location_id: int,
    current_qty: int = 20,
    reserved_qty: int = 0,
) -> dict[str, object]:
    return {
        "carton_number": carton_number,
        "product_packaging_id": packaging_id,
        "current_location_id": location_id,
        "current_qty": current_qty,
        "reserved_qty": reserved_qty,
        "status": "available",
        "expires_at": None,
    }


def test_create_carton_uses_packaging_capacity(db_client: TestClient) -> None:
    packaging_id, location_id = create_carton_dependencies(db_client, "001")
    response = db_client.post(
        "/cartons",
        json=carton_payload(
            "test-koli-001",
            packaging_id,
            location_id,
            current_qty=20,
            reserved_qty=5,
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["carton_number"] == "TEST-KOLI-001"
    assert body["capacity_qty"] == 24
    assert body["current_qty"] == 20
    assert body["reserved_qty"] == 5
    assert body["available_qty"] == 15
    assert body["status"] == "reserved"


def test_create_carton_rejects_capacity_overflow(db_client: TestClient) -> None:
    packaging_id, location_id = create_carton_dependencies(
        db_client,
        "002",
        units_per_carton=12,
    )
    response = db_client.post(
        "/cartons",
        json=carton_payload(
            "TEST-KOLI-002",
            packaging_id,
            location_id,
            current_qty=13,
        ),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "current_qty cannot exceed carton capacity 12"


def test_create_carton_rejects_duplicate_number(db_client: TestClient) -> None:
    packaging_id, location_id = create_carton_dependencies(db_client, "003")
    payload = carton_payload("test-koli-003", packaging_id, location_id)

    first_response = db_client.post("/cartons", json=payload)
    payload["carton_number"] = "TEST-KOLI-003"
    duplicate_response = db_client.post("/cartons", json=payload)

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409


def test_carton_quantity_and_status_lifecycle(db_client: TestClient) -> None:
    packaging_id, location_id = create_carton_dependencies(db_client, "004")
    create_response = db_client.post(
        "/cartons",
        json=carton_payload("TEST-KOLI-004", packaging_id, location_id),
    )
    assert create_response.status_code == 201
    carton_id = create_response.json()["id"]

    reserve_response = db_client.patch(
        f"/cartons/{carton_id}",
        json={"reserved_qty": 5},
    )
    quarantine_response = db_client.patch(
        f"/cartons/{carton_id}",
        json={"status": "quarantined"},
    )
    empty_response = db_client.patch(
        f"/cartons/{carton_id}",
        json={"current_qty": 0, "reserved_qty": 0},
    )
    release_response = db_client.patch(
        f"/cartons/{carton_id}",
        json={"status": "available"},
    )

    assert reserve_response.status_code == 200
    assert reserve_response.json()["available_qty"] == 15
    assert reserve_response.json()["status"] == "reserved"
    assert quarantine_response.json()["status"] == "quarantined"
    assert empty_response.json()["status"] == "quarantined"
    assert release_response.json()["status"] == "depleted"


def test_list_cartons_filters_status_and_location(db_client: TestClient) -> None:
    packaging_id, location_id = create_carton_dependencies(db_client, "005")
    create_response = db_client.post(
        "/cartons",
        json=carton_payload(
            "TEST-KOLI-005",
            packaging_id,
            location_id,
            reserved_qty=5,
        ),
    )
    assert create_response.status_code == 201
    carton_id = create_response.json()["id"]

    response = db_client.get(
        "/cartons",
        params={"status": "reserved", "location_id": location_id},
    )

    assert response.status_code == 200
    assert any(item["id"] == carton_id for item in response.json())
