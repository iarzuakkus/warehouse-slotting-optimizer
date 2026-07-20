"""Sipariş satırı koli ayırma endpoint testleri."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import carton_type_dimensions, create_warehouse_rack


def create_allocation_context(
    db_client: TestClient,
    db_session: Session,
    suffix: str,
    ordered_qty: int = 10,
    carton_qty: int = 20,
) -> tuple[int, int, int]:
    product = db_client.post(
        "/products",
        json={
            "sku": f"TEST-ALLOCATION-PRODUCT-{suffix}",
            "name": "Koli Ayirma Test Urunu",
            "unit_weight_kg": "0.500",
            "is_active": True,
        },
    )
    carton_type = db_client.post(
        "/carton-types",
        json={
            "code": f"TEST-ALLOCATION-CT-{suffix}",
            "name": "Koli Ayirma Test Tipi",
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
        aisle=f"TEST-ALLOCATION-{suffix}",
        bay="01",
    )
    location = db_client.post(
        "/warehouse-locations",
        json={
            "aisle": f"TEST-ALLOCATION-{suffix}",
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
            "carton_number": f"TEST-ALLOCATION-CARTON-{suffix}",
            "product_packaging_id": packaging.json()["id"],
            "current_location_id": location.json()["id"],
            "current_qty": carton_qty,
            "reserved_qty": 0,
        },
    )
    order = db_client.post(
        "/orders",
        json={"order_number": f"TEST-ALLOCATION-ORDER-{suffix}"},
    )
    assert carton.status_code == 201
    assert order.status_code == 201

    line = db_client.post(
        f"/orders/{order.json()['id']}/lines",
        json={"product_id": product.json()["id"], "ordered_qty": ordered_qty},
    )
    assert line.status_code == 201
    return order.json()["id"], line.json()["id"], carton.json()["id"]


def allocation_url(order_id: int, line_id: int) -> str:
    return f"/orders/{order_id}/lines/{line_id}/allocations"


def test_carton_allocation_lifecycle(db_client: TestClient, db_session: Session) -> None:
    order_id, line_id, carton_id = create_allocation_context(
        db_client, db_session, "001"
    )
    url = allocation_url(order_id, line_id)

    create_response = db_client.post(
        url,
        json={"carton_id": carton_id, "allocated_qty": 5},
    )
    assert create_response.status_code == 201
    allocation_id = create_response.json()["id"]

    carton_after_create = db_client.get(f"/cartons/{carton_id}")
    list_response = db_client.get(url)
    update_response = db_client.patch(
        f"{url}/{allocation_id}",
        json={"allocated_qty": 7},
    )
    cancel_response = db_client.patch(
        f"{url}/{allocation_id}",
        json={"status": "cancelled"},
    )
    carton_after_cancel = db_client.get(f"/cartons/{carton_id}")

    assert carton_after_create.json()["reserved_qty"] == 5
    assert carton_after_create.json()["status"] == "reserved"
    assert [item["id"] for item in list_response.json()] == [allocation_id]
    assert update_response.status_code == 200
    assert update_response.json()["allocated_qty"] == 7
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    assert carton_after_cancel.json()["reserved_qty"] == 0
    assert carton_after_cancel.json()["status"] == "available"


def test_rejects_duplicate_carton_allocation(db_client: TestClient, db_session: Session) -> None:
    order_id, line_id, carton_id = create_allocation_context(
        db_client, db_session, "002"
    )
    url = allocation_url(order_id, line_id)
    payload = {"carton_id": carton_id, "allocated_qty": 2}

    first = db_client.post(url, json=payload)
    duplicate = db_client.post(url, json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 409


def test_rejects_carton_from_different_product(db_client: TestClient, db_session: Session) -> None:
    order_id, line_id, _ = create_allocation_context(
        db_client, db_session, "003-A"
    )
    _, _, other_carton_id = create_allocation_context(
        db_client, db_session, "003-B"
    )

    response = db_client.post(
        allocation_url(order_id, line_id),
        json={"carton_id": other_carton_id, "allocated_qty": 1},
    )

    assert response.status_code == 409


def test_rejects_quantity_above_carton_stock(db_client: TestClient, db_session: Session) -> None:
    order_id, line_id, carton_id = create_allocation_context(
        db_client,
        db_session,
        "004",
        ordered_qty=10,
        carton_qty=5,
    )

    response = db_client.post(
        allocation_url(order_id, line_id),
        json={"carton_id": carton_id, "allocated_qty": 6},
    )

    assert response.status_code == 409


def test_rejects_quantity_above_order_need(db_client: TestClient, db_session: Session) -> None:
    order_id, line_id, carton_id = create_allocation_context(
        db_client,
        db_session,
        "005",
        ordered_qty=5,
        carton_qty=20,
    )

    response = db_client.post(
        allocation_url(order_id, line_id),
        json={"carton_id": carton_id, "allocated_qty": 6},
    )

    assert response.status_code == 409
