"""Runtime fiziksel koli yerlestirme entegrasyon testleri."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.inventory import WarehouseRack
from tests.factories import carton_type_dimensions, create_warehouse_rack


def isolate_active_racks(session: Session) -> None:
    session.execute(update(WarehouseRack).values(is_active=False))
    session.flush()


def create_packaging(
    client: TestClient,
    *,
    suffix: str,
    unit_weight_kg: str = "1.000",
    inner_length_cm: Decimal = Decimal("40.00"),
    inner_width_cm: Decimal = Decimal("30.00"),
    inner_height_cm: Decimal = Decimal("25.00"),
) -> int:
    product = client.post(
        "/products",
        json={
            "sku": f"PHYSICAL-PRODUCT-{suffix}",
            "name": f"Physical Product {suffix}",
            "unit_weight_kg": unit_weight_kg,
            "is_active": True,
        },
    )
    carton_type = client.post(
        "/carton-types",
        json={
            "code": f"PHYSICAL-CT-{suffix}",
            "name": f"Physical Carton Type {suffix}",
            **carton_type_dimensions(
                inner_length_cm=inner_length_cm,
                inner_width_cm=inner_width_cm,
                inner_height_cm=inner_height_cm,
            ),
            "max_weight_kg": "1000.000",
            "is_active": True,
        },
    )
    assert product.status_code == 201
    assert carton_type.status_code == 201

    packaging = client.post(
        "/product-packaging",
        json={
            "product_id": product.json()["id"],
            "carton_type_id": carton_type.json()["id"],
            "units_per_carton": 100,
            "is_default": True,
        },
    )
    assert packaging.status_code == 201
    return packaging.json()["id"]


def create_location(
    client: TestClient,
    *,
    aisle: str,
    slot: str,
    max_weight_kg: str,
) -> int:
    response = client.post(
        "/warehouse-locations",
        json={
            "aisle": aisle,
            "bay": "B01",
            "level": "L01",
            "slot": slot,
            "max_weight_kg": max_weight_kg,
            "distance_from_dispatch_m": "10.00",
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_carton(
    client: TestClient,
    *,
    suffix: str,
    packaging_id: int,
    location_id: int,
    current_qty: int,
) -> dict[str, object]:
    response = client.post(
        "/cartons",
        json={
            "carton_number": f"PHYSICAL-CARTON-{suffix}",
            "product_packaging_id": packaging_id,
            "current_location_id": location_id,
            "current_qty": current_qty,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_uses_ninety_degree_rotation_when_required(
    db_client: TestClient,
    db_session: Session,
) -> None:
    isolate_active_racks(db_session)
    create_warehouse_rack(
        db_session,
        aisle="PHYSICAL-ROTATION",
        bay="B01",
        level_count=1,
        slots_per_level=1,
        usable_slot_width_cm=Decimal("35.00"),
        usable_depth_cm=Decimal("45.00"),
    )
    location_id = create_location(
        db_client,
        aisle="PHYSICAL-ROTATION",
        slot="S01",
        max_weight_kg="100.000",
    )
    packaging_id = create_packaging(db_client, suffix="ROTATION")

    carton = create_carton(
        db_client,
        suffix="ROTATION",
        packaging_id=packaging_id,
        location_id=location_id,
        current_qty=10,
    )

    assert carton["current_location_id"] == location_id
    assert carton["rotation_degrees"] == 90
    assert carton["position_x_cm"] == "0.00"
    assert carton["position_y_cm"] == "0.00"


def test_tries_another_location_when_preferred_location_exceeds_weight(
    db_client: TestClient,
    db_session: Session,
) -> None:
    isolate_active_racks(db_session)
    create_warehouse_rack(
        db_session,
        aisle="PHYSICAL-ALTERNATIVE",
        bay="B01",
        level_count=1,
        slots_per_level=2,
    )
    preferred_id = create_location(
        db_client,
        aisle="PHYSICAL-ALTERNATIVE",
        slot="S01",
        max_weight_kg="5.000",
    )
    alternative_id = create_location(
        db_client,
        aisle="PHYSICAL-ALTERNATIVE",
        slot="S02",
        max_weight_kg="100.000",
    )
    packaging_id = create_packaging(db_client, suffix="ALTERNATIVE")

    carton = create_carton(
        db_client,
        suffix="ALTERNATIVE",
        packaging_id=packaging_id,
        location_id=preferred_id,
        current_qty=10,
    )

    assert carton["current_location_id"] == alternative_id
    assert carton["position_x_cm"] == "0.00"


def test_leaves_carton_unassigned_when_no_location_can_fit_it(
    db_client: TestClient,
    db_session: Session,
) -> None:
    isolate_active_racks(db_session)
    create_warehouse_rack(
        db_session,
        aisle="PHYSICAL-NO-FIT",
        bay="B01",
        level_count=1,
        slots_per_level=1,
        usable_slot_width_cm=Decimal("30.00"),
        usable_depth_cm=Decimal("30.00"),
    )
    location_id = create_location(
        db_client,
        aisle="PHYSICAL-NO-FIT",
        slot="S01",
        max_weight_kg="100.000",
    )
    packaging_id = create_packaging(db_client, suffix="NO-FIT")

    carton = create_carton(
        db_client,
        suffix="NO-FIT",
        packaging_id=packaging_id,
        location_id=location_id,
        current_qty=10,
    )

    assert carton["current_location_id"] is None
    assert carton["position_x_cm"] is None
    assert carton["position_y_cm"] is None
    assert carton["position_z_cm"] is None
    assert carton["rotation_degrees"] is None


def test_multiple_cartons_are_placed_without_overlap(
    db_client: TestClient,
    db_session: Session,
) -> None:
    isolate_active_racks(db_session)
    create_warehouse_rack(
        db_session,
        aisle="PHYSICAL-COLLISION",
        bay="B01",
        level_count=1,
        slots_per_level=1,
    )
    location_id = create_location(
        db_client,
        aisle="PHYSICAL-COLLISION",
        slot="S01",
        max_weight_kg="100.000",
    )
    packaging_id = create_packaging(db_client, suffix="COLLISION")

    first = create_carton(
        db_client,
        suffix="COLLISION-1",
        packaging_id=packaging_id,
        location_id=location_id,
        current_qty=10,
    )
    second = create_carton(
        db_client,
        suffix="COLLISION-2",
        packaging_id=packaging_id,
        location_id=location_id,
        current_qty=10,
    )

    assert first["current_location_id"] == location_id
    assert second["current_location_id"] == location_id
    assert first["position_x_cm"] == "0.00"
    assert second["position_x_cm"] == "42.00"
    assert first["position_y_cm"] == second["position_y_cm"] == "0.00"
    assert first["position_z_cm"] == second["position_z_cm"] == "0.00"
