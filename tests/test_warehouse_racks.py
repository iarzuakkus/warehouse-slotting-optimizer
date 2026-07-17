"""Warehouse rack detail endpoint tests."""

from fastapi.testclient import TestClient


def create_location(
    client: TestClient,
    *,
    aisle: str,
    bay: str,
    level: str,
    slot: str,
    is_active: bool = True,
) -> dict[str, object]:
    response = client.post(
        "/warehouse-locations",
        json={
            "aisle": aisle,
            "bay": bay,
            "level": level,
            "slot": slot,
            "max_weight_kg": 500,
            "distance_from_dispatch_m": 10,
            "is_active": is_active,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_get_warehouse_rack_detail(db_client: TestClient) -> None:
    second_location = create_location(
        db_client,
        aisle="test-rack-a",
        bay="b01",
        level="l02",
        slot="s01",
        is_active=False,
    )
    first_location = create_location(
        db_client,
        aisle="test-rack-a",
        bay="b01",
        level="l01",
        slot="s01",
    )

    response = db_client.get("/warehouse-racks/test-rack-a/b01")

    assert response.status_code == 200
    body = response.json()
    assert body["aisle"] == "TEST-RACK-A"
    assert body["bay"] == "B01"
    assert body["level_count"] == 2
    assert body["location_count"] == 2
    assert body["active_location_count"] == 1
    assert body["carton_count"] == 0
    assert body["product_count"] == 0
    assert body["total_max_weight_kg"] == "1000.000"
    assert body["total_used_weight_kg"] == "0.000"
    assert body["weight_utilization_percent"] == "0.00"
    assert [location["id"] for location in body["locations"]] == [
        first_location["id"],
        second_location["id"],
    ]
    assert body["locations"][0]["aisle"] == "TEST-RACK-A"
    assert body["locations"][0]["bay"] == "B01"
    assert body["locations"][0]["created_at"]
    assert body["locations"][0]["updated_at"]


def test_get_warehouse_rack_returns_404_for_unknown_rack(
    db_client: TestClient,
) -> None:
    response = db_client.get("/warehouse-racks/unknown/b99")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Warehouse rack UNKNOWN/B99 not found"
    }


def test_get_warehouse_rack_resolves_frontend_synthetic_aisle_alias(
    db_client: TestClient,
) -> None:
    location = create_location(
        db_client,
        aisle="SYN-A987",
        bay="B01",
        level="L01",
        slot="S01",
    )

    response = db_client.get("/warehouse-racks/A987/B01")

    assert response.status_code == 200
    body = response.json()
    assert body["aisle"] == "SYN-A987"
    assert body["locations"][0]["id"] == location["id"]


def test_get_warehouse_rack_does_not_invent_missing_capacity(
    db_client: TestClient,
) -> None:
    create_response = db_client.post(
        "/warehouse-locations",
        json={
            "aisle": "TEST-RACK-NO-CAPACITY",
            "bay": "B01",
            "level": "L01",
            "slot": "S01",
            "max_weight_kg": None,
            "distance_from_dispatch_m": 10,
            "is_active": True,
        },
    )
    assert create_response.status_code == 201

    response = db_client.get("/warehouse-racks/test-rack-no-capacity/b01")

    assert response.status_code == 200
    body = response.json()
    assert body["total_max_weight_kg"] is None
    assert body["total_used_weight_kg"] == "0.000"
    assert body["weight_utilization_percent"] is None
    assert body["locations"][0]["weight_utilization_percent"] is None


def test_get_warehouse_rack_includes_carton_product_and_weight_details(
    db_client: TestClient,
) -> None:
    location = create_location(
        db_client,
        aisle="test-rack-weight",
        bay="b01",
        level="l01",
        slot="s01",
    )
    product_response = db_client.post(
        "/products",
        json={
            "sku": "TEST-RACK-PRODUCT",
            "name": "Rack Test Product",
            "unit_weight_kg": 1.25,
            "is_active": True,
        },
    )
    carton_type_response = db_client.post(
        "/carton-types",
        json={
            "code": "TEST-RACK-CARTON-TYPE",
            "name": "Rack Test Carton Type",
            "inner_length_cm": 40,
            "inner_width_cm": 30,
            "inner_height_cm": 25,
            "max_weight_kg": 100,
            "is_active": True,
        },
    )
    assert product_response.status_code == 201
    assert carton_type_response.status_code == 201
    packaging_response = db_client.post(
        "/product-packaging",
        json={
            "product_id": product_response.json()["id"],
            "carton_type_id": carton_type_response.json()["id"],
            "units_per_carton": 500,
            "is_default": True,
        },
    )
    assert packaging_response.status_code == 201
    carton_response = db_client.post(
        "/cartons",
        json={
            "carton_number": "TEST-RACK-CARTON",
            "product_packaging_id": packaging_response.json()["id"],
            "current_location_id": location["id"],
            "current_qty": 350,
            "reserved_qty": 25,
            "status": "available",
            "expires_at": None,
        },
    )
    assert carton_response.status_code == 201

    response = db_client.get("/warehouse-racks/test-rack-weight/b01")

    assert response.status_code == 200
    body = response.json()
    assert body["carton_count"] == 1
    assert body["product_count"] == 1
    assert body["total_used_weight_kg"] == "437.500"
    assert body["weight_utilization_percent"] == "87.50"
    location_body = body["locations"][0]
    assert location_body["used_weight_kg"] == "437.500"
    assert location_body["weight_utilization_percent"] == "87.50"
    carton = location_body["cartons"][0]
    assert carton["available_qty"] == 325
    assert carton["product"]["sku"] == "TEST-RACK-PRODUCT"
    assert carton["product"]["unit_weight_kg"] == "1.250"
    assert carton["packaging"]["carton_type_code"] == "TEST-RACK-CARTON-TYPE"
