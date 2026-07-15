"""Depo konumu CRUD endpoint testleri."""

from fastapi.testclient import TestClient


def location_payload(
    aisle: str,
    bay: str,
    level: str,
    slot: str,
) -> dict[str, object]:
    return {
        "aisle": aisle,
        "bay": bay,
        "level": level,
        "slot": slot,
        "max_weight_kg": 750,
        "distance_from_dispatch_m": 12.5,
        "is_active": True,
    }


def list_all_locations(db_client: TestClient) -> list[dict[str, object]]:
    locations: list[dict[str, object]] = []
    offset = 0
    while True:
        response = db_client.get(
            "/warehouse-locations",
            params={"offset": offset, "limit": 100},
        )
        assert response.status_code == 200
        page = response.json()
        locations.extend(page)
        if len(page) < 100:
            return locations
        offset += 100


def test_create_warehouse_location(db_client: TestClient) -> None:
    response = db_client.post(
        "/warehouse-locations",
        json=location_payload("test-a", "01", "zemin", "sol"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["aisle"] == "TEST-A"
    assert body["level"] == "ZEMIN"
    assert body["slot"] == "SOL"
    assert body["max_weight_kg"] == "750.000"
    assert body["distance_from_dispatch_m"] == "12.50"


def test_create_location_rejects_duplicate_coordinates(db_client: TestClient) -> None:
    first_response = db_client.post(
        "/warehouse-locations",
        json=location_payload("test-b", "01", "01", "01"),
    )
    duplicate_response = db_client.post(
        "/warehouse-locations",
        json=location_payload("TEST-B", "01", "01", "01"),
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409


def test_warehouse_location_lifecycle(db_client: TestClient) -> None:
    create_response = db_client.post(
        "/warehouse-locations",
        json=location_payload("TEST-C", "01", "01", "01"),
    )
    assert create_response.status_code == 201
    location_id = create_response.json()["id"]

    get_response = db_client.get(f"/warehouse-locations/{location_id}")
    listed_locations = list_all_locations(db_client)
    update_response = db_client.patch(
        f"/warehouse-locations/{location_id}",
        json={"slot": "02", "distance_from_dispatch_m": 15},
    )
    deactivate_response = db_client.delete(f"/warehouse-locations/{location_id}")

    assert get_response.status_code == 200
    assert any(item["id"] == location_id for item in listed_locations)
    assert update_response.status_code == 200
    assert update_response.json()["slot"] == "02"
    assert update_response.json()["distance_from_dispatch_m"] == "15.00"
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False


def test_partial_update_rejects_coordinate_collision(db_client: TestClient) -> None:
    first_response = db_client.post(
        "/warehouse-locations",
        json=location_payload("TEST-D", "01", "01", "01"),
    )
    second_response = db_client.post(
        "/warehouse-locations",
        json=location_payload("TEST-D", "01", "01", "02"),
    )
    assert first_response.status_code == 201
    assert second_response.status_code == 201

    response = db_client.patch(
        f"/warehouse-locations/{second_response.json()['id']}",
        json={"slot": "01"},
    )

    assert response.status_code == 409


def test_update_location_rejects_null_coordinate(db_client: TestClient) -> None:
    create_response = db_client.post(
        "/warehouse-locations",
        json=location_payload("TEST-E", "01", "01", "01"),
    )
    assert create_response.status_code == 201

    response = db_client.patch(
        f"/warehouse-locations/{create_response.json()['id']}",
        json={"aisle": None},
    )

    assert response.status_code == 422
