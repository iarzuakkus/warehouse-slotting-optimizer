"""Koli toplama hareketi endpoint testleri."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import carton_type_dimensions, create_warehouse_rack


def create_pick_context(
    db_client: TestClient,
    db_session: Session,
    suffix: str,
    allocated_qty: int = 5,
    activate_order: bool = True,
) -> tuple[int, int, int, int, int]:
    product = db_client.post(
        "/products",
        json={
            "sku": f"TEST-PICK-PRODUCT-{suffix}",
            "name": "Toplama Test Urunu",
            "unit_weight_kg": "0.500",
            "is_active": True,
        },
    )
    carton_type = db_client.post(
        "/carton-types",
        json={
            "code": f"TEST-PICK-CT-{suffix}",
            "name": "Toplama Test Koli Tipi",
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
    create_warehouse_rack(
        db_session,
        aisle=f"TEST-PICK-{suffix}",
        bay="01",
    )
    location = db_client.post(
        "/warehouse-locations",
        json={
            "aisle": f"TEST-PICK-{suffix}",
            "bay": "01",
            "level": "01",
            "slot": "01",
            "max_weight_kg": 750,
            "distance_from_dispatch_m": 10,
            "is_active": True,
        },
    )
    assert packaging.status_code == 201
    assert location.status_code == 201

    carton = db_client.post(
        "/cartons",
        json={
            "carton_number": f"TEST-PICK-CARTON-{suffix}",
            "product_packaging_id": packaging.json()["id"],
            "current_location_id": location.json()["id"],
            "current_qty": 20,
        },
    )
    order = db_client.post(
        "/orders",
        json={"order_number": f"TEST-PICK-ORDER-{suffix}"},
    )
    assert carton.status_code == 201
    assert order.status_code == 201

    order_id = order.json()["id"]
    line = db_client.post(
        f"/orders/{order_id}/lines",
        json={
            "product_id": product.json()["id"],
            "ordered_qty": allocated_qty,
        },
    )
    assert line.status_code == 201
    line_id = line.json()["id"]

    allocation = db_client.post(
        f"/orders/{order_id}/lines/{line_id}/allocations",
        json={
            "carton_id": carton.json()["id"],
            "allocated_qty": allocated_qty,
        },
    )
    assert allocation.status_code == 201

    if activate_order:
        status_response = db_client.patch(
            f"/orders/{order_id}",
            json={"status": "allocated"},
        )
        assert status_response.status_code == 200

    return (
        order_id,
        line_id,
        allocation.json()["id"],
        carton.json()["id"],
        location.json()["id"],
    )


def pick_url(order_id: int, line_id: int, allocation_id: int) -> str:
    return (
        f"/orders/{order_id}/lines/{line_id}"
        f"/allocations/{allocation_id}/picks"
    )


def test_pick_operation_lifecycle(db_client: TestClient, db_session: Session) -> None:
    order_id, line_id, allocation_id, carton_id, location_id = (
        create_pick_context(db_client, db_session, "001")
    )
    url = pick_url(order_id, line_id, allocation_id)

    first_pick = db_client.post(
        url,
        json={"quantity": 2, "operator_reference": "OP-001"},
    )
    allocation_after_first = db_client.get(
        f"/orders/{order_id}/lines/{line_id}/allocations/{allocation_id}"
    )
    carton_after_first = db_client.get(f"/cartons/{carton_id}")
    order_after_first = db_client.get(f"/orders/{order_id}")

    second_pick = db_client.post(
        url,
        json={"quantity": 3, "operator_reference": "OP-002"},
    )
    allocation_after_second = db_client.get(
        f"/orders/{order_id}/lines/{line_id}/allocations/{allocation_id}"
    )
    line_after_second = db_client.get(f"/orders/{order_id}/lines/{line_id}")
    carton_after_second = db_client.get(f"/cartons/{carton_id}")
    order_after_second = db_client.get(f"/orders/{order_id}")
    history = db_client.get(url)

    assert first_pick.status_code == 201
    assert first_pick.json()["location_id"] == location_id
    assert allocation_after_first.json()["picked_qty"] == 2
    assert allocation_after_first.json()["status"] == "picking"
    assert carton_after_first.json()["current_qty"] == 18
    assert carton_after_first.json()["reserved_qty"] == 3
    assert order_after_first.json()["status"] == "picking"

    assert second_pick.status_code == 201
    assert allocation_after_second.json()["picked_qty"] == 5
    assert allocation_after_second.json()["status"] == "picked"
    assert line_after_second.json()["fulfilled_qty"] == 5
    assert carton_after_second.json()["current_qty"] == 15
    assert carton_after_second.json()["reserved_qty"] == 0
    assert order_after_second.json()["status"] == "completed"
    assert len(history.json()) == 2


def test_rejects_pick_while_order_is_pending(db_client: TestClient, db_session: Session) -> None:
    order_id, line_id, allocation_id, _, _ = create_pick_context(
        db_client,
        db_session,
        "002",
        activate_order=False,
    )

    response = db_client.post(
        pick_url(order_id, line_id, allocation_id),
        json={"quantity": 1},
    )

    assert response.status_code == 409


def test_rejects_pick_above_allocated_quantity(db_client: TestClient, db_session: Session) -> None:
    order_id, line_id, allocation_id, _, _ = create_pick_context(
        db_client,
        db_session,
        "003",
        allocated_qty=3,
    )

    response = db_client.post(
        pick_url(order_id, line_id, allocation_id),
        json={"quantity": 4},
    )

    assert response.status_code == 409


def test_rejects_pick_from_quarantined_carton(db_client: TestClient, db_session: Session) -> None:
    order_id, line_id, allocation_id, carton_id, _ = create_pick_context(
        db_client,
        db_session,
        "004",
    )
    quarantine = db_client.patch(
        f"/cartons/{carton_id}",
        json={"status": "quarantined"},
    )
    assert quarantine.status_code == 200

    response = db_client.post(
        pick_url(order_id, line_id, allocation_id),
        json={"quantity": 1},
    )

    assert response.status_code == 409


def test_rejects_missing_allocation(db_client: TestClient, db_session: Session) -> None:
    order_id, line_id, _, _, _ = create_pick_context(
        db_client, db_session, "005"
    )

    response = db_client.post(
        pick_url(order_id, line_id, 999999999),
        json={"quantity": 1},
    )

    assert response.status_code == 404
