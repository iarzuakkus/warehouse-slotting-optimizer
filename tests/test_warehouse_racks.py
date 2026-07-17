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
    max_weight_kg: float | None = 500,
) -> dict[str, object]:
    response = client.post(
        "/warehouse-locations",
        json={
            "aisle": aisle,
            "bay": bay,
            "level": level,
            "slot": slot,
            "max_weight_kg": max_weight_kg,
            "distance_from_dispatch_m": 10,
            "is_active": is_active,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_packaging(
    client: TestClient,
    *,
    suffix: str,
    unit_weight_kg: float | None,
) -> tuple[int, int]:
    product_response = client.post(
        "/products",
        json={
            "sku": f"RACK-SUMMARY-PRODUCT-{suffix}",
            "name": f"Rack Summary Product {suffix}",
            "unit_weight_kg": unit_weight_kg,
            "is_active": True,
        },
    )
    carton_type_response = client.post(
        "/carton-types",
        json={
            "code": f"RACK-SUMMARY-CT-{suffix}",
            "name": f"Rack Summary Carton Type {suffix}",
            "inner_length_cm": 40,
            "inner_width_cm": 30,
            "inner_height_cm": 25,
            "max_weight_kg": 1000,
            "is_active": True,
        },
    )
    assert product_response.status_code == 201
    assert carton_type_response.status_code == 201
    packaging_response = client.post(
        "/product-packaging",
        json={
            "product_id": product_response.json()["id"],
            "carton_type_id": carton_type_response.json()["id"],
            "units_per_carton": 1000,
            "is_default": True,
        },
    )
    assert packaging_response.status_code == 201
    return packaging_response.json()["id"], product_response.json()["id"]


def create_carton(
    client: TestClient,
    *,
    suffix: str,
    packaging_id: int,
    location_id: int,
    current_qty: int,
) -> None:
    response = client.post(
        "/cartons",
        json={
            "carton_number": f"RACK-SUMMARY-CARTON-{suffix}",
            "product_packaging_id": packaging_id,
            "current_location_id": location_id,
            "current_qty": current_qty,
            "reserved_qty": 0,
            "status": "available",
            "expires_at": None,
        },
    )
    assert response.status_code == 201


def find_rack_summary(
    client: TestClient,
    aisle: str,
    bay: str,
) -> dict[str, object]:
    response = client.get("/warehouse-racks", params={"offset": 0, "limit": 100})
    assert response.status_code == 200
    return next(
        rack
        for rack in response.json()
        if rack["aisle"] == aisle and rack["bay"] == bay
    )


SUMMARY_FIELDS = {
    "aisle",
    "bay",
    "level_count",
    "location_count",
    "active_location_count",
    "carton_count",
    "product_count",
    "total_max_weight_kg",
    "total_used_weight_kg",
    "weight_utilization_percent",
}


def test_list_warehouse_racks_returns_sorted_lightweight_summaries(
    db_client: TestClient,
) -> None:
    create_location(
        db_client,
        aisle="000-SUMMARY-B",
        bay="B02",
        level="L01",
        slot="S01",
    )
    create_location(
        db_client,
        aisle="000-SUMMARY-A",
        bay="B01",
        level="L01",
        slot="S01",
        is_active=False,
    )

    response = db_client.get("/warehouse-racks", params={"limit": 100})

    assert response.status_code == 200
    summaries = [
        rack for rack in response.json() if rack["aisle"].startswith("000-SUMMARY-")
    ]
    assert [(rack["aisle"], rack["bay"]) for rack in summaries] == [
        ("000-SUMMARY-A", "B01"),
        ("000-SUMMARY-B", "B02"),
    ]
    assert set(summaries[0]) == SUMMARY_FIELDS
    assert summaries[0]["carton_count"] == 0
    assert summaries[0]["product_count"] == 0
    assert summaries[0]["active_location_count"] == 0


def test_list_warehouse_racks_pagination(db_client: TestClient) -> None:
    create_location(
        db_client,
        aisle="000-PAGE-A",
        bay="B01",
        level="L01",
        slot="S01",
    )
    create_location(
        db_client,
        aisle="000-PAGE-B",
        bay="B01",
        level="L01",
        slot="S01",
    )

    first_two = db_client.get(
        "/warehouse-racks", params={"offset": 0, "limit": 2}
    )
    first = db_client.get("/warehouse-racks", params={"offset": 0, "limit": 1})
    second = db_client.get("/warehouse-racks", params={"offset": 1, "limit": 1})

    assert first_two.status_code == 200
    assert first_two.json() == first.json() + second.json()
    assert db_client.get("/warehouse-racks", params={"offset": -1}).status_code == 422
    assert db_client.get("/warehouse-racks", params={"limit": 0}).status_code == 422
    assert db_client.get("/warehouse-racks", params={"limit": 101}).status_code == 422


def test_list_warehouse_racks_counts_products_and_matches_detail(
    db_client: TestClient,
) -> None:
    first_location = create_location(
        db_client,
        aisle="000-SUMMARY-WEIGHT",
        bay="B01",
        level="L01",
        slot="S01",
    )
    second_location = create_location(
        db_client,
        aisle="000-SUMMARY-WEIGHT",
        bay="B01",
        level="L02",
        slot="S01",
    )
    first_packaging_id, _ = create_packaging(
        db_client,
        suffix="WEIGHT-A",
        unit_weight_kg=1.25,
    )
    second_packaging_id, _ = create_packaging(
        db_client,
        suffix="WEIGHT-B",
        unit_weight_kg=0.5,
    )
    create_carton(
        db_client,
        suffix="WEIGHT-A1",
        packaging_id=first_packaging_id,
        location_id=int(first_location["id"]),
        current_qty=10,
    )
    create_carton(
        db_client,
        suffix="WEIGHT-A2",
        packaging_id=first_packaging_id,
        location_id=int(second_location["id"]),
        current_qty=20,
    )
    create_carton(
        db_client,
        suffix="WEIGHT-B1",
        packaging_id=second_packaging_id,
        location_id=int(second_location["id"]),
        current_qty=10,
    )

    summary = find_rack_summary(db_client, "000-SUMMARY-WEIGHT", "B01")
    detail_response = db_client.get("/warehouse-racks/000-SUMMARY-WEIGHT/B01")

    assert detail_response.status_code == 200
    assert summary["level_count"] == 2
    assert summary["location_count"] == 2
    assert summary["carton_count"] == 3
    assert summary["product_count"] == 2
    assert summary["total_max_weight_kg"] == "1000.000"
    assert summary["total_used_weight_kg"] == "42.500"
    assert summary["weight_utilization_percent"] == "4.25"
    detail_summary = {
        field: detail_response.json()[field] for field in SUMMARY_FIELDS
    }
    assert summary == detail_summary


def test_list_warehouse_racks_preserves_null_capacity_behavior(
    db_client: TestClient,
) -> None:
    create_location(
        db_client,
        aisle="000-SUMMARY-NO-CAP",
        bay="B01",
        level="L01",
        slot="S01",
        max_weight_kg=None,
    )

    summary = find_rack_summary(db_client, "000-SUMMARY-NO-CAP", "B01")

    assert summary["total_max_weight_kg"] is None
    assert summary["total_used_weight_kg"] == "0.000"
    assert summary["weight_utilization_percent"] is None


def test_list_warehouse_racks_preserves_unknown_unit_weight_behavior(
    db_client: TestClient,
) -> None:
    location = create_location(
        db_client,
        aisle="000-SUMMARY-NO-WEIGHT",
        bay="B01",
        level="L01",
        slot="S01",
    )
    packaging_id, _ = create_packaging(
        db_client,
        suffix="NO-WEIGHT",
        unit_weight_kg=None,
    )
    create_carton(
        db_client,
        suffix="NO-WEIGHT",
        packaging_id=packaging_id,
        location_id=int(location["id"]),
        current_qty=10,
    )

    summary = find_rack_summary(db_client, "000-SUMMARY-NO-WEIGHT", "B01")

    assert summary["carton_count"] == 1
    assert summary["product_count"] == 1
    assert summary["total_max_weight_kg"] == "500.000"
    assert summary["total_used_weight_kg"] is None
    assert summary["weight_utilization_percent"] is None


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
