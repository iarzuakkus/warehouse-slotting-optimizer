"""Simulation scenario API and persistence integration tests."""

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.inventory import Carton, WarehouseLocation
from tests.factories import carton_type_dimensions, create_warehouse_rack


RACK_SCENE_FIELDS = {
    "aisle",
    "bay",
    "width_cm",
    "depth_cm",
    "total_height_cm",
    "level_clear_height_cm",
    "level_count",
    "slots_per_level",
    "location_count",
    "active_location_count",
    "locations",
}
LOCATION_SCENE_FIELDS = {
    "id",
    "level",
    "slot",
    "is_active",
    "usable_width_cm",
    "usable_depth_cm",
    "usable_height_cm",
    "max_weight_kg",
    "used_weight_kg",
    "weight_utilization_percent",
    "volume_utilization_percent",
    "cartons",
}
CARTON_SCENE_FIELDS = {
    "id",
    "carton_number",
    "carton_type_code",
    "outer_length_cm",
    "outer_width_cm",
    "outer_height_cm",
    "position_x_cm",
    "position_y_cm",
    "position_z_cm",
    "rotation_degrees",
}


def create_scenario(
    client: TestClient,
    suffix: str,
    aisle: str,
    *,
    seed: int = 42,
) -> int:
    response = client.post(
        "/simulation-scenarios",
        json={
            "name": f"Simulation Scenario {suffix}",
            "seed": seed,
            "aisle_filter": [aisle],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_location(
    client: TestClient,
    session: Session,
    *,
    aisle: str,
    slot: str,
    distance: str,
    active: bool = True,
    max_weight: str = "1000",
) -> int:
    create_warehouse_rack(
        session,
        aisle=aisle,
        bay="B001",
        level_count=1,
        slots_per_level=3,
    )
    response = client.post(
        "/warehouse-locations",
        json={
            "aisle": aisle,
            "bay": "B001",
            "level": "L01",
            "slot": slot,
            "max_weight_kg": max_weight,
            "distance_from_dispatch_m": distance,
            "is_active": active,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_packaging(client: TestClient, suffix: str) -> int:
    product = client.post(
        "/products",
        json={
            "sku": f"SIM-PRODUCT-{suffix}",
            "name": f"Simulation Product {suffix}",
            "unit_weight_kg": "1.000",
            "unit_length_cm": "10.00",
            "unit_width_cm": "8.00",
            "unit_height_cm": "6.00",
            "is_active": True,
        },
    )
    carton_type = client.post(
        "/carton-types",
        json={
            "code": f"SIM-CT-{suffix}",
            "name": f"Simulation Carton Type {suffix}",
            **carton_type_dimensions(
                inner_length_cm=20,
                inner_width_cm=18,
                inner_height_cm=16,
            ),
            "max_weight_kg": "100.000",
            "is_active": True,
        },
    )
    assert product.status_code == 201, product.text
    assert carton_type.status_code == 201, carton_type.text
    packaging = client.post(
        "/product-packaging",
        json={
            "product_id": product.json()["id"],
            "carton_type_id": carton_type.json()["id"],
            "units_per_carton": 50,
            "is_default": True,
        },
    )
    assert packaging.status_code == 201, packaging.text
    return packaging.json()["id"]


def create_carton(
    client: TestClient,
    *,
    suffix: str,
    packaging_id: int,
    location_id: int,
) -> dict[str, Any]:
    response = client.post(
        "/cartons",
        json={
            "carton_number": f"SIM-CARTON-{suffix}",
            "product_packaging_id": packaging_id,
            "current_location_id": location_id,
            "current_qty": 10,
            "reserved_qty": 0,
            "status": "available",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["current_location_id"] == location_id
    return response.json()


def create_movement_context(
    client: TestClient,
    session: Session,
    suffix: str,
) -> tuple[str, int, int, int]:
    aisle = f"TEST-SIM-{suffix}"
    target_id = create_location(
        client,
        session,
        aisle=aisle,
        slot="S01",
        distance="5",
    )
    source_id = create_location(
        client,
        session,
        aisle=aisle,
        slot="S02",
        distance="100",
    )
    packaging_id = create_packaging(client, suffix)
    created_carton = create_carton(
        client,
        suffix=suffix,
        packaging_id=packaging_id,
        location_id=source_id,
    )
    return aisle, source_id, target_id, created_carton["id"]


def test_scenario_crud_pagination_and_pending_result_conflict(
    db_client: TestClient,
) -> None:
    aisle = "TEST-SIM-CRUD"
    first_id = create_scenario(db_client, "CRUD-1", aisle, seed=1)
    second_id = create_scenario(db_client, "CRUD-2", aisle, seed=2)

    page = db_client.get(
        "/simulation-scenarios",
        params={"offset": 0, "limit": 1, "status": "pending"},
    )
    updated = db_client.patch(
        f"/simulation-scenarios/{first_id}",
        json={"name": "Updated Simulation", "minimize_moves": False},
    )
    scene_before_run = db_client.get(
        f"/simulation-scenarios/{first_id}/scene"
    )
    deleted = db_client.delete(f"/simulation-scenarios/{second_id}")
    missing = db_client.get(f"/simulation-scenarios/{second_id}")

    assert page.status_code == 200
    assert len(page.json()) == 1
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Simulation"
    assert updated.json()["parameters"]["minimize_moves"] is False
    assert scene_before_run.status_code == 409
    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert db_client.get(
        "/simulation-scenarios", params={"limit": 101}
    ).status_code == 422


def test_run_preserves_real_layout_and_returns_moves_and_scene(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle, source_id, target_id, carton_id = create_movement_context(
        db_client,
        db_session,
        "RUN",
    )
    scenario_id = create_scenario(db_client, "RUN", aisle)
    original = db_session.get(Carton, carton_id)
    original_placement = (
        original.current_location_id,
        original.position_x_cm,
        original.position_y_cm,
        original.position_z_cm,
        original.rotation_degrees,
    )

    run = db_client.post(f"/simulation-scenarios/{scenario_id}/run")
    moves = db_client.get(f"/simulation-scenarios/{scenario_id}/moves")
    initial_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/scene", params={"step": 0}
    )
    proposed_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/scene"
    )
    db_session.expire_all()
    persisted = db_session.get(Carton, carton_id)

    assert run.status_code == 200, run.text
    assert run.json()["status"] == "completed"
    assert Decimal(run.json()["progress_percent"]) == Decimal("100")
    assert set(run.json()["result"]) == {
        "current",
        "proposed",
        "objective_improvement_percent",
        "estimated_duration_seconds",
        "total_movement_distance_m",
    }
    assert moves.status_code == 200
    assert moves.json()["move_count"] >= 1
    first_move = moves.json()["moves"][0]
    assert first_move["from_location_id"] == source_id
    assert first_move["to_location_id"] == target_id
    assert first_move["travel_distance_m"] == "95.00"
    assert first_move["reasons"]
    assert initial_scene.status_code == 200
    assert proposed_scene.status_code == 200
    _assert_scene_contract(proposed_scene.json())
    assert _carton_location(initial_scene.json(), carton_id) == source_id
    assert _carton_location(proposed_scene.json(), carton_id) == target_id
    assert (
        persisted.current_location_id,
        persisted.position_x_cm,
        persisted.position_y_cm,
        persisted.position_z_cm,
        persisted.rotation_degrees,
    ) == original_placement


def test_same_seed_produces_same_persisted_scenario_result(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle, _, _, _ = create_movement_context(
        db_client,
        db_session,
        "SEED",
    )
    first_id = create_scenario(db_client, "SEED-1", aisle, seed=77)
    second_id = create_scenario(db_client, "SEED-2", aisle, seed=77)

    first_run = db_client.post(f"/simulation-scenarios/{first_id}/run")
    second_run = db_client.post(f"/simulation-scenarios/{second_id}/run")
    first_moves = db_client.get(
        f"/simulation-scenarios/{first_id}/moves"
    ).json()["moves"]
    second_moves = db_client.get(
        f"/simulation-scenarios/{second_id}/moves"
    ).json()["moves"]

    assert first_run.status_code == 200, first_run.text
    assert second_run.status_code == 200, second_run.text
    assert first_run.json()["result"] == second_run.json()["result"]
    assert [_stable_move(move) for move in first_moves] == [
        _stable_move(move) for move in second_moves
    ]


def test_inactive_location_is_not_used_as_a_simulation_target(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle = "TEST-SIM-INACTIVE"
    inactive_id = create_location(
        db_client,
        db_session,
        aisle=aisle,
        slot="S01",
        distance="1",
        active=False,
    )
    active_target_id = create_location(
        db_client,
        db_session,
        aisle=aisle,
        slot="S02",
        distance="5",
    )
    source_id = create_location(
        db_client,
        db_session,
        aisle=aisle,
        slot="S03",
        distance="100",
    )
    packaging_id = create_packaging(db_client, "INACTIVE")
    create_carton(
        db_client,
        suffix="INACTIVE",
        packaging_id=packaging_id,
        location_id=source_id,
    )
    scenario_id = create_scenario(db_client, "INACTIVE", aisle)

    run = db_client.post(f"/simulation-scenarios/{scenario_id}/run")
    moves = db_client.get(
        f"/simulation-scenarios/{scenario_id}/moves"
    ).json()["moves"]

    assert run.status_code == 200, run.text
    placed_targets = {
        move["to_location_id"]
        for move in moves
        if move["result_status"] == "placed"
    }
    assert inactive_id not in placed_targets
    assert active_target_id in placed_targets


def test_unplaceable_carton_is_reported_and_removed_from_proposed_scene(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle = "TEST-SIM-UNPLACED"
    location_id = create_location(
        db_client,
        db_session,
        aisle=aisle,
        slot="S01",
        distance="10",
        max_weight="100",
    )
    packaging_id = create_packaging(db_client, "UNPLACED")
    created = create_carton(
        db_client,
        suffix="UNPLACED",
        packaging_id=packaging_id,
        location_id=location_id,
    )
    db_location = db_session.get(WarehouseLocation, location_id)
    db_location.max_weight_kg = 1
    db_session.flush()
    scenario_id = create_scenario(db_client, "UNPLACED", aisle)

    run = db_client.post(f"/simulation-scenarios/{scenario_id}/run")
    moves = db_client.get(f"/simulation-scenarios/{scenario_id}/moves")
    scene = db_client.get(f"/simulation-scenarios/{scenario_id}/scene")

    assert run.status_code == 200, run.text
    assert run.json()["result"]["proposed"]["unplaced_carton_count"] == 1
    assert moves.status_code == 200
    assert moves.json()["unplaced_count"] == 1
    assert moves.json()["moves"][0]["result_status"] == "unplaced"
    assert moves.json()["moves"][0]["to_location_id"] is None
    assert moves.json()["moves"][0]["unplaced_reason"]
    assert _carton_location(scene.json(), created["id"]) is None


def _stable_move(move: dict[str, Any]) -> dict[str, Any]:
    ignored = {"id"}
    return {key: value for key, value in move.items() if key not in ignored}


def _assert_scene_contract(scene: list[dict[str, Any]]) -> None:
    assert scene
    assert set(scene[0]) == RACK_SCENE_FIELDS
    assert scene[0]["locations"]
    assert set(scene[0]["locations"][0]) == LOCATION_SCENE_FIELDS
    cartons = [
        carton
        for location in scene[0]["locations"]
        for carton in location["cartons"]
    ]
    assert cartons
    assert set(cartons[0]) == CARTON_SCENE_FIELDS


def _carton_location(
    scene: list[dict[str, Any]],
    carton_id: int,
) -> int | None:
    for rack in scene:
        for location in rack["locations"]:
            if any(
                carton["id"] == carton_id for carton in location["cartons"]
            ):
                return location["id"]
    return None
