"""Simulation move batch endpoint integration tests."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.inventory import Carton, WarehouseLocation
from app.models.optimization import OptimizationAssignment, OptimizationRun
from tests.test_simulation_scenarios import (
    _carton_location,
    create_carton,
    create_location,
    create_movement_context,
    create_packaging,
    create_scenario,
)


def test_batch_list_and_detail_preserve_existing_moves_response(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle, source_id, target_id, carton_id = create_movement_context(
        db_client,
        db_session,
        "BATCH-LIFECYCLE",
    )
    scenario_id = create_scenario(
        db_client,
        "BATCH-LIFECYCLE",
        aisle,
        seed=91,
    )
    run = db_client.post(f"/simulation-scenarios/{scenario_id}/run")
    moves_before = db_client.get(
        f"/simulation-scenarios/{scenario_id}/moves"
    )

    batches = db_client.get(
        f"/simulation-scenarios/{scenario_id}/move-batches"
    )
    source_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/scene",
        params={"step": 0},
    )
    proposed_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/scene"
    )
    detail = db_client.get(
        f"/simulation-scenarios/{scenario_id}/move-batches/1"
    )
    moves_after = db_client.get(
        f"/simulation-scenarios/{scenario_id}/moves"
    )

    assert run.status_code == 200, run.text
    assert batches.status_code == 200, batches.text
    payload = batches.json()
    assert payload["scenario_id"] == scenario_id
    assert payload["equipment_type"] == "cart"
    assert payload["batch_count"] == 1
    assert payload["carton_move_count"] == 1
    assert Decimal(payload["operational_distance_m"]) == Decimal("200")
    assert Decimal(payload["individual_distance_m"]) == Decimal("95")
    assert Decimal(payload["estimated_duration_seconds"]) > 0
    assert Decimal(payload["capacity_utilization_percent"]) <= 100
    assert payload["unbatched_items"] == []
    assert payload["validation_errors"] == []
    batch_source_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene",
        params={"step": 0},
    )
    batch_proposed_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene",
        params={"step": payload["batch_count"]},
    )
    excessive_step = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene",
        params={"step": payload["batch_count"] + 1},
    )
    negative_step = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene",
        params={"step": -1},
    )
    missing_step = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene"
    )
    assert source_scene.status_code == 200
    assert proposed_scene.status_code == 200
    assert batch_source_scene.status_code == 200
    assert batch_source_scene.json() == source_scene.json()
    assert batch_proposed_scene.status_code == 200
    assert batch_proposed_scene.json() == proposed_scene.json()
    assert excessive_step.status_code == 409
    assert negative_step.status_code == 422
    assert missing_step.status_code == 422

    batch = payload["batches"][0]
    assert batch["sequence"] == 1
    assert batch["carton_count"] == 1
    assert Decimal(batch["estimated_distance_m"]) == Decimal("200")
    assert batch["move_sequences"] == [
        moves_before.json()["moves"][0]["sequence"]
    ]
    assert batch["items"][0]["carton_id"] == carton_id
    assert batch["items"][0]["from_location_id"] == source_id
    assert batch["items"][0]["to_location_id"] == target_id
    assert [stop["type"] for stop in batch["stops"]] == [
        "pickup",
        "dropoff",
    ]
    assert detail.status_code == 200
    assert detail.json() == batch
    assert moves_after.json() == moves_before.json()


def test_multiple_cartons_share_batch_within_operational_limits(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle, source_id, _, first_carton_id = create_movement_context(
        db_client,
        db_session,
        "BATCH-MULTI-CARTON",
    )
    first_carton = db_session.get(Carton, first_carton_id)
    assert first_carton is not None
    second_carton = create_carton(
        db_client,
        suffix="BATCH-MULTI-CARTON-SECOND",
        packaging_id=first_carton.product_packaging_id,
        location_id=source_id,
    )
    scenario = db_client.post(
        "/simulation-scenarios",
        json={
            "name": "Multiple Carton Batch Scenario",
            "seed": 96,
            "aisle_filter": [aisle],
            "equipment_type": "cart",
            "max_batch_weight_kg": "250",
            "max_batch_volume_m3": "1.2",
            "max_cartons_per_batch": 12,
        },
    )
    assert scenario.status_code == 201, scenario.text
    scenario_id = scenario.json()["id"]

    run = db_client.post(f"/simulation-scenarios/{scenario_id}/run")
    moves = db_client.get(f"/simulation-scenarios/{scenario_id}/moves")
    batches = db_client.get(
        f"/simulation-scenarios/{scenario_id}/move-batches"
    )

    assert run.status_code == 200, run.text
    assert moves.status_code == 200, moves.text
    assert batches.status_code == 200, batches.text
    payload = batches.json()
    assert payload["carton_move_count"] > payload["batch_count"]
    multi_carton_batches = [
        batch for batch in payload["batches"] if batch["carton_count"] > 1
    ]
    assert multi_carton_batches

    all_batch_sequences: set[int] = set()
    all_batch_carton_ids: set[int] = set()
    for batch in payload["batches"]:
        assert batch["carton_count"] <= 12
        assert Decimal(batch["total_weight_kg"]) <= Decimal("250")
        assert Decimal(batch["total_volume_m3"]) <= Decimal("1.2")
        item_sequences = {
            item["move_sequence"] for item in batch["items"]
        }
        item_carton_ids = {item["carton_id"] for item in batch["items"]}
        stop_carton_ids = {
            carton_id
            for stop in batch["stops"]
            for carton_id in stop["carton_ids"]
        }
        assert set(batch["move_sequences"]) == item_sequences
        assert stop_carton_ids == item_carton_ids
        all_batch_sequences.update(item_sequences)
        all_batch_carton_ids.update(item_carton_ids)

    placed_moves = {
        move["sequence"]: move["carton_id"]
        for move in moves.json()["moves"]
        if move["result_status"] == "placed"
    }
    assert all_batch_sequences == set(placed_moves)
    assert all_batch_carton_ids == set(placed_moves.values())
    assert {first_carton_id, second_carton["id"]}.issubset(
        all_batch_carton_ids
    )


def test_batch_scene_applies_batch_order_instead_of_assignment_prefix(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle = "TEST-SIM-BATCH-SCENE-ORDER"
    first_location_id = create_location(
        db_client,
        db_session,
        aisle=aisle,
        slot="S01",
        distance="100",
    )
    second_location_id = create_location(
        db_client,
        db_session,
        aisle=aisle,
        slot="S02",
        distance="50",
    )
    third_location_id = create_location(
        db_client,
        db_session,
        aisle=aisle,
        slot="S03",
        distance="5",
    )
    packaging_id = create_packaging(db_client, "BATCH-SCENE-ORDER")
    first_carton = create_carton(
        db_client,
        suffix="BATCH-SCENE-ORDER-FIRST",
        packaging_id=packaging_id,
        location_id=first_location_id,
    )
    second_carton = create_carton(
        db_client,
        suffix="BATCH-SCENE-ORDER-SECOND",
        packaging_id=packaging_id,
        location_id=second_location_id,
    )
    scenario_id = create_scenario(
        db_client,
        "BATCH-SCENE-ORDER",
        aisle,
        seed=97,
    )
    run = db_client.post(f"/simulation-scenarios/{scenario_id}/run")
    assert run.status_code == 200, run.text

    scenario = db_session.get(OptimizationRun, scenario_id)
    assert scenario is not None
    scenario.parameters = {
        **scenario.parameters,
        "max_cartons_per_batch": 1,
    }
    assignments = {
        assignment.carton_id: assignment
        for assignment in scenario.assignments
    }
    first_assignment = assignments[first_carton["id"]]
    second_assignment = assignments[second_carton["id"]]
    first_assignment.sequence_number = 1001
    second_assignment.sequence_number = 1002
    db_session.flush()
    _configure_placed_assignment(
        first_assignment,
        sequence=1,
        from_location_id=first_location_id,
        to_location_id=second_location_id,
        carton=db_session.get(Carton, first_carton["id"]),
    )
    _configure_placed_assignment(
        second_assignment,
        sequence=2,
        from_location_id=second_location_id,
        to_location_id=third_location_id,
        carton=db_session.get(Carton, second_carton["id"]),
    )
    db_session.flush()
    db_session.expire_all()

    batches = db_client.get(
        f"/simulation-scenarios/{scenario_id}/move-batches"
    )
    batch_step_one = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene",
        params={"step": 1},
    )
    old_step_one_before = db_client.get(
        f"/simulation-scenarios/{scenario_id}/scene",
        params={"step": 1},
    )
    old_step_one_after = db_client.get(
        f"/simulation-scenarios/{scenario_id}/scene",
        params={"step": 1},
    )

    assert batches.status_code == 200, batches.text
    assert [
        batch["move_sequences"] for batch in batches.json()["batches"]
    ] == [[2], [1]]
    assert batch_step_one.status_code == 200, batch_step_one.text
    assert (
        _carton_location(batch_step_one.json(), first_carton["id"])
        == first_location_id
    )
    assert (
        _carton_location(batch_step_one.json(), second_carton["id"])
        == third_location_id
    )
    assert old_step_one_before.status_code == 200
    assert old_step_one_after.json() == old_step_one_before.json()
    assert (
        _carton_location(old_step_one_before.json(), first_carton["id"])
        == second_location_id
    )
    assert (
        _carton_location(old_step_one_before.json(), second_carton["id"])
        == second_location_id
    )


def test_batch_scene_applies_swap_cycle_atomically(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle = "TEST-SIM-BATCH-SCENE-CYCLE"
    first_location_id = create_location(
        db_client,
        db_session,
        aisle=aisle,
        slot="S01",
        distance="20",
    )
    second_location_id = create_location(
        db_client,
        db_session,
        aisle=aisle,
        slot="S02",
        distance="30",
    )
    packaging_id = create_packaging(db_client, "BATCH-SCENE-CYCLE")
    first_carton = create_carton(
        db_client,
        suffix="BATCH-SCENE-CYCLE-FIRST",
        packaging_id=packaging_id,
        location_id=first_location_id,
    )
    second_carton = create_carton(
        db_client,
        suffix="BATCH-SCENE-CYCLE-SECOND",
        packaging_id=packaging_id,
        location_id=second_location_id,
    )
    scenario_id = create_scenario(
        db_client,
        "BATCH-SCENE-CYCLE",
        aisle,
        seed=98,
    )
    run = db_client.post(f"/simulation-scenarios/{scenario_id}/run")
    assert run.status_code == 200, run.text

    scenario = db_session.get(OptimizationRun, scenario_id)
    assert scenario is not None
    scenario.parameters = {
        **scenario.parameters,
        "max_cartons_per_batch": 2,
    }
    for assignment in list(scenario.assignments):
        db_session.delete(assignment)
    db_session.flush()
    first_assignment = OptimizationAssignment(
        optimization_run_id=scenario_id,
        carton_id=first_carton["id"],
    )
    second_assignment = OptimizationAssignment(
        optimization_run_id=scenario_id,
        carton_id=second_carton["id"],
    )
    _configure_placed_assignment(
        first_assignment,
        sequence=1,
        from_location_id=first_location_id,
        to_location_id=second_location_id,
        carton=db_session.get(Carton, first_carton["id"]),
    )
    _configure_placed_assignment(
        second_assignment,
        sequence=2,
        from_location_id=second_location_id,
        to_location_id=first_location_id,
        carton=db_session.get(Carton, second_carton["id"]),
    )
    db_session.add_all([first_assignment, second_assignment])
    db_session.flush()
    db_session.expire_all()

    batches = db_client.get(
        f"/simulation-scenarios/{scenario_id}/move-batches"
    )
    staging_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene",
        params={"step": 1},
    )

    assert batches.status_code == 200, batches.text
    payload = batches.json()
    assert payload["batch_count"] == 3
    assert payload["requires_staging_buffer"] is True
    assert len(payload["staging_move_sequences"]) == 1
    staged_sequence = payload["staging_move_sequences"][0]
    moves = db_client.get(
        f"/simulation-scenarios/{scenario_id}/moves"
    ).json()["moves"]
    carton_id_by_sequence = {
        move["sequence"]: move["carton_id"] for move in moves
    }
    staged_carton_id = carton_id_by_sequence[staged_sequence]
    other_carton_id = (
        {first_carton["id"], second_carton["id"]} - {staged_carton_id}
    ).pop()
    source_by_carton = {
        first_carton["id"]: first_location_id,
        second_carton["id"]: second_location_id,
    }
    target_by_carton = {
        first_carton["id"]: second_location_id,
        second_carton["id"]: first_location_id,
    }
    assert payload["batches"][0]["staged_move_sequences"] == [
        staged_sequence
    ]
    assert payload["batches"][2]["finalized_move_sequences"] == [
        staged_sequence
    ]
    for batch in payload["batches"]:
        assert batch["move_sequences"] == [
            item["move_sequence"] for item in batch["items"]
        ]
        assert batch["carton_count"] == len(batch["items"])
    assert payload["batches"][2]["move_sequences"] == [staged_sequence]
    assert [
        item["move_sequence"]
        for item in payload["batches"][2]["items"]
    ] == [staged_sequence]
    serialized_item_count = sum(
        len(batch["items"]) for batch in payload["batches"]
    ) + len(payload["unbatched_items"])
    assert payload["carton_move_count"] == serialized_item_count
    assert staging_scene.status_code == 200, staging_scene.text
    assert (
        _carton_location(staging_scene.json(), staged_carton_id)
        is None
    )
    assert (
        _carton_location(staging_scene.json(), other_carton_id)
        == source_by_carton[other_carton_id]
    )
    transport_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene",
        params={"step": 2},
    )
    final_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene",
        params={"step": 3},
    )
    normal_final_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/scene"
    )
    assert transport_scene.status_code == 200, transport_scene.text
    assert _carton_location(
        transport_scene.json(), staged_carton_id
    ) is None
    assert (
        _carton_location(transport_scene.json(), other_carton_id)
        == target_by_carton[other_carton_id]
    )
    assert final_scene.status_code == 200, final_scene.text
    assert normal_final_scene.status_code == 200
    assert (
        _carton_location(final_scene.json(), staged_carton_id)
        == target_by_carton[staged_carton_id]
    )
    assert (
        _carton_location(final_scene.json(), other_carton_id)
        == target_by_carton[other_carton_id]
    )
    assert final_scene.json() == normal_final_scene.json()


def test_batch_scene_rejects_out_of_bounds_target_placement(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle, _, _, carton_id = create_movement_context(
        db_client,
        db_session,
        "BATCH-OOB",
    )
    scenario_id = create_scenario(
        db_client,
        "BATCH-OOB",
        aisle,
        seed=99,
    )
    run = db_client.post(f"/simulation-scenarios/{scenario_id}/run")
    assert run.status_code == 200, run.text
    scenario = db_session.get(OptimizationRun, scenario_id)
    assert scenario is not None
    assignment = next(
        item
        for item in scenario.assignments
        if item.carton_id == carton_id
    )
    assignment.proposed_position_x_cm = Decimal("95.00")
    db_session.flush()
    db_session.expire_all()

    scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene",
        params={"step": 1},
    )

    assert scene.status_code == 409
    assert "exceeds location boundaries" in scene.json()["detail"]


def test_batch_scene_rejects_unsupported_target_placement(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle, _, _, carton_id = create_movement_context(
        db_client,
        db_session,
        "BATCH-UNSUP",
    )
    scenario_id = create_scenario(
        db_client,
        "BATCH-UNSUP",
        aisle,
        seed=100,
    )
    run = db_client.post(f"/simulation-scenarios/{scenario_id}/run")
    assert run.status_code == 200, run.text
    scenario = db_session.get(OptimizationRun, scenario_id)
    assert scenario is not None
    assignment = next(
        item
        for item in scenario.assignments
        if item.carton_id == carton_id
    )
    assignment.proposed_position_z_cm = Decimal("10.00")
    db_session.flush()
    db_session.expire_all()

    scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene",
        params={"step": 1},
    )

    assert scene.status_code == 409
    assert "not fully supported" in scene.json()["detail"]


def test_over_capacity_placed_move_is_reported_as_unbatched(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle, _, _, carton_id = create_movement_context(
        db_client,
        db_session,
        "BATCH-OVER-CAPACITY",
    )
    created = db_client.post(
        "/simulation-scenarios",
        json={
            "name": "Over Capacity Batch Scenario",
            "seed": 92,
            "aisle_filter": [aisle],
            "equipment_type": "forklift",
            "max_batch_weight_kg": "5",
            "max_batch_volume_m3": "1.2",
            "max_cartons_per_batch": 12,
        },
    )
    assert created.status_code == 201, created.text
    scenario_id = created.json()["id"]

    run = db_client.post(f"/simulation-scenarios/{scenario_id}/run")
    batches = db_client.get(
        f"/simulation-scenarios/{scenario_id}/move-batches"
    )
    source_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/scene",
        params={"step": 0},
    )
    batch_scene = db_client.get(
        f"/simulation-scenarios/{scenario_id}/batch-scene",
        params={"step": 0},
    )

    assert run.status_code == 200, run.text
    assert batches.status_code == 200, batches.text
    payload = batches.json()
    assert payload["equipment_type"] == "forklift"
    assert payload["carton_move_count"] == 1
    assert payload["batch_count"] == 0
    assert payload["batches"] == []
    assert payload["unbatched_items"][0]["carton_id"] == carton_id
    assert {
        error["code"] for error in payload["validation_errors"]
    } == {"max_batch_weight_exceeded"}
    assert source_scene.status_code == 200
    assert batch_scene.status_code == 200
    assert batch_scene.json() == source_scene.json()


def test_unplaced_simulation_move_is_excluded_from_batches(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle = "TEST-SIM-BATCH-UNPLACED"
    location_id = create_location(
        db_client,
        db_session,
        aisle=aisle,
        slot="S01",
        distance="10",
        max_weight="100",
    )
    packaging_id = create_packaging(db_client, "BATCH-UNPLACED")
    create_carton(
        db_client,
        suffix="BATCH-UNPLACED",
        packaging_id=packaging_id,
        location_id=location_id,
    )
    location = db_session.get(WarehouseLocation, location_id)
    location.max_weight_kg = 1
    db_session.flush()
    scenario_id = create_scenario(
        db_client,
        "BATCH-UNPLACED",
        aisle,
        seed=93,
    )

    run = db_client.post(f"/simulation-scenarios/{scenario_id}/run")
    moves = db_client.get(f"/simulation-scenarios/{scenario_id}/moves")
    batches = db_client.get(
        f"/simulation-scenarios/{scenario_id}/move-batches"
    )

    assert run.status_code == 200, run.text
    assert moves.status_code == 200
    assert moves.json()["unplaced_count"] == 1
    assert batches.status_code == 200
    assert batches.json()["carton_move_count"] == 0
    assert batches.json()["batch_count"] == 0
    assert batches.json()["batches"] == []
    assert batches.json()["unbatched_items"] == []


def _configure_placed_assignment(
    assignment: OptimizationAssignment,
    *,
    sequence: int,
    from_location_id: int,
    to_location_id: int,
    carton: Carton | None,
    proposed_x_cm: Decimal = Decimal("0.00"),
    proposed_y_cm: Decimal = Decimal("0.00"),
    proposed_z_cm: Decimal = Decimal("0.00"),
) -> None:
    assert carton is not None
    assignment.sequence_number = sequence
    assignment.result_status = "placed"
    assignment.from_location_id = from_location_id
    assignment.to_location_id = to_location_id
    assignment.from_position_x_cm = carton.position_x_cm
    assignment.from_position_y_cm = carton.position_y_cm
    assignment.from_position_z_cm = carton.position_z_cm
    assignment.from_rotation_degrees = carton.rotation_degrees
    assignment.proposed_position_x_cm = proposed_x_cm
    assignment.proposed_position_y_cm = proposed_y_cm
    assignment.proposed_position_z_cm = proposed_z_cm
    assignment.proposed_rotation_degrees = 0


def test_batch_plan_is_deterministic_for_same_seed_and_layout(
    db_client: TestClient,
    db_session: Session,
) -> None:
    aisle, _, _, _ = create_movement_context(
        db_client,
        db_session,
        "BATCH-SEED",
    )
    first_id = create_scenario(
        db_client,
        "BATCH-SEED-1",
        aisle,
        seed=94,
    )
    second_id = create_scenario(
        db_client,
        "BATCH-SEED-2",
        aisle,
        seed=94,
    )
    first_run = db_client.post(
        f"/simulation-scenarios/{first_id}/run"
    )
    second_run = db_client.post(
        f"/simulation-scenarios/{second_id}/run"
    )

    first = db_client.get(
        f"/simulation-scenarios/{first_id}/move-batches"
    ).json()
    second = db_client.get(
        f"/simulation-scenarios/{second_id}/move-batches"
    ).json()
    first.pop("scenario_id")
    second.pop("scenario_id")

    assert first_run.status_code == 200, first_run.text
    assert second_run.status_code == 200, second_run.text
    assert first == second


def test_invalid_scenario_sequence_and_pending_scenario_responses(
    db_client: TestClient,
) -> None:
    pending_id = create_scenario(
        db_client,
        "BATCH-PENDING",
        "TEST-SIM-BATCH-PENDING",
        seed=95,
    )

    missing_scenario = db_client.get(
        "/simulation-scenarios/999999999/move-batches"
    )
    pending = db_client.get(
        f"/simulation-scenarios/{pending_id}/move-batches"
    )
    invalid_sequence = db_client.get(
        f"/simulation-scenarios/{pending_id}/move-batches/0"
    )

    assert missing_scenario.status_code == 404
    assert pending.status_code == 409
    assert invalid_sequence.status_code == 422
