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
    assert body["location_count"] == 2
    assert body["active_location_count"] == 1
    assert [location["id"] for location in body["locations"]] == [
        first_location["id"],
        second_location["id"],
    ]


def test_get_warehouse_rack_returns_404_for_unknown_rack(
    db_client: TestClient,
) -> None:
    response = db_client.get("/warehouse-racks/unknown/b99")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Warehouse rack UNKNOWN/B99 not found"
    }
