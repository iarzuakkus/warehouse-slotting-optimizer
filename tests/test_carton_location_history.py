"""Koli taşıma ve konum geçmişi endpoint testleri."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import carton_type_dimensions, create_warehouse_rack


def create_location(
    db_client: TestClient,
    db_session: Session,
    suffix: str,
    slot: str,
) -> int:
    aisle = f"TEST-MOVEMENT-{suffix}"
    create_warehouse_rack(db_session, aisle=aisle, bay="01")
    response = db_client.post(
        "/warehouse-locations",
        json={
            "aisle": aisle,
            "bay": "01",
            "level": "01",
            "slot": slot,
            "max_weight_kg": 750,
            "distance_from_dispatch_m": 10,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_movement_context(
    db_client: TestClient,
    db_session: Session,
    suffix: str,
) -> tuple[int, int, int]:
    product = db_client.post(
        "/products",
        json={
            "sku": f"TEST-MOVEMENT-PRODUCT-{suffix}",
            "name": "Koli Hareket Test Urunu",
            "unit_weight_kg": "0.500",
            "is_active": True,
        },
    )
    carton_type = db_client.post(
        "/carton-types",
        json={
            "code": f"TEST-MOVEMENT-CT-{suffix}",
            "name": "Koli Hareket Test Tipi",
            **carton_type_dimensions(),
            "max_weight_kg": 20,
            "is_active": True,
        },
    )
    assert product.status_code == 201
    assert carton_type.status_code == 201

    packaging = db_client.post(
        "/product-packaging",
        json={
            "product_id": product.json()["id"],
            "carton_type_id": carton_type.json()["id"],
            "units_per_carton": 24,
            "is_default": True,
        },
    )
    source_id = create_location(db_client, db_session, f"{suffix}-SOURCE", "01")
    target_id = create_location(db_client, db_session, f"{suffix}-TARGET", "02")
    assert packaging.status_code == 201

    carton = db_client.post(
        "/cartons",
        json={
            "carton_number": f"TEST-MOVEMENT-CARTON-{suffix}",
            "product_packaging_id": packaging.json()["id"],
            "current_location_id": source_id,
            "current_qty": 20,
        },
    )
    assert carton.status_code == 201
    return carton.json()["id"], source_id, target_id


def test_carton_movement_lifecycle(db_client: TestClient, db_session: Session) -> None:
    carton_id, source_id, target_id = create_movement_context(
        db_client, db_session, "001"
    )
    url = f"/cartons/{carton_id}/movements"

    movement = db_client.post(
        url,
        json={"to_location_id": target_id, "reason": "Raf iyilestirmesi"},
    )
    assert movement.status_code == 201
    history_id = movement.json()["id"]

    carton = db_client.get(f"/cartons/{carton_id}")
    history = db_client.get(url)
    detail = db_client.get(f"{url}/{history_id}")

    assert movement.json()["from_location_id"] == source_id
    assert movement.json()["to_location_id"] == target_id
    assert carton.json()["current_location_id"] == target_id
    assert carton.json()["position_x_cm"] == "0.00"
    assert carton.json()["position_y_cm"] == "0.00"
    assert carton.json()["position_z_cm"] == "0.00"
    assert carton.json()["rotation_degrees"] == 0
    assert [item["id"] for item in history.json()] == [history_id]
    assert detail.status_code == 200


def test_rejects_movement_to_same_location(db_client: TestClient, db_session: Session) -> None:
    carton_id, source_id, _ = create_movement_context(db_client, db_session, "002")

    response = db_client.post(
        f"/cartons/{carton_id}/movements",
        json={"to_location_id": source_id},
    )

    assert response.status_code == 409


def test_rejects_movement_to_inactive_location(db_client: TestClient, db_session: Session) -> None:
    carton_id, _, target_id = create_movement_context(db_client, db_session, "003")
    deactivate = db_client.delete(f"/warehouse-locations/{target_id}")
    assert deactivate.status_code == 200

    response = db_client.post(
        f"/cartons/{carton_id}/movements",
        json={"to_location_id": target_id},
    )

    assert response.status_code == 409


def test_rejects_missing_target_location(db_client: TestClient, db_session: Session) -> None:
    carton_id, _, _ = create_movement_context(db_client, db_session, "004")

    response = db_client.post(
        f"/cartons/{carton_id}/movements",
        json={"to_location_id": 999999999},
    )

    assert response.status_code == 404


def test_can_remove_carton_from_location(db_client: TestClient, db_session: Session) -> None:
    carton_id, source_id, _ = create_movement_context(db_client, db_session, "005")

    movement = db_client.post(
        f"/cartons/{carton_id}/movements",
        json={"to_location_id": None, "reason": "Sevkiyat alani"},
    )
    carton = db_client.get(f"/cartons/{carton_id}")

    assert movement.status_code == 201
    assert movement.json()["from_location_id"] == source_id
    assert movement.json()["to_location_id"] is None
    assert carton.json()["current_location_id"] is None
    assert carton.json()["position_x_cm"] is None
    assert carton.json()["position_y_cm"] is None
    assert carton.json()["position_z_cm"] is None
    assert carton.json()["rotation_degrees"] is None
