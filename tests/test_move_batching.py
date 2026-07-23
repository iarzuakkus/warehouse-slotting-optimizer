"""Deterministic operational move batching tests."""

from decimal import Decimal

from app.algorithms.move_batching import (
    MoveBatchCandidate,
    MoveBatchLimits,
    _build_dependencies,
    plan_move_batches,
)
from app.algorithms.carton_placement import PlacedCarton


def decimal(value: str) -> Decimal:
    return Decimal(value)


def limits(
    *,
    weight: str = "250",
    volume: str = "1.2",
    cartons: int = 12,
) -> MoveBatchLimits:
    return MoveBatchLimits(
        equipment_type="cart",
        max_weight_kg=decimal(weight),
        max_volume_m3=decimal(volume),
        max_cartons=cartons,
    )


def move(
    sequence: int,
    *,
    sku: str | None = None,
    weight: str = "50",
    volume: str = "0.2",
    source: int | None = None,
    target: int | None = None,
    source_key: tuple[int, int, int, int] | None = None,
    target_key: tuple[int, int, int, int] | None = None,
    source_placement: PlacedCarton | None = None,
    target_placement: PlacedCarton | None = None,
) -> MoveBatchCandidate:
    effective_source = source if source is not None else sequence
    effective_target = target if target is not None else sequence + 100
    return MoveBatchCandidate(
        move_sequence=sequence,
        carton_id=sequence,
        carton_number=f"CARTON-{sequence:03d}",
        sku=sku or f"SKU-{sequence:03d}",
        weight_kg=decimal(weight),
        volume_m3=decimal(volume),
        from_location_id=effective_source,
        to_location_id=effective_target,
        from_location_key=source_key or (1, effective_source, 1, 1),
        to_location_key=target_key or (2, effective_target, 1, 1),
        individual_distance_m=decimal("10"),
        individual_duration_seconds=decimal("15"),
        source_placement=source_placement,
        target_placement=target_placement,
    )


def placement(
    carton_id: int,
    *,
    x: str,
    y: str = "0",
    z: str = "0",
    width: str = "20",
    depth: str = "20",
    height: str = "20",
) -> PlacedCarton:
    return PlacedCarton(
        carton_id=carton_id,
        position_x_cm=decimal(x),
        position_y_cm=decimal(y),
        position_z_cm=decimal(z),
        occupied_width_cm=decimal(width),
        occupied_depth_cm=decimal(depth),
        occupied_height_cm=decimal(height),
        rotation_degrees=0,
    )


def test_weight_limit_splits_batches_without_exceeding_capacity() -> None:
    plan = plan_move_batches(
        [
            move(1, weight="100"),
            move(2, weight="100"),
            move(3, weight="100"),
        ],
        limits(weight="200"),
        seed=1,
    )

    assert [len(batch.items) for batch in plan.batches] == [2, 1]
    assert all(
        batch.total_weight_kg <= decimal("200")
        for batch in plan.batches
    )


def test_volume_limit_splits_batches_without_exceeding_capacity() -> None:
    plan = plan_move_batches(
        [
            move(1, volume="0.7"),
            move(2, volume="0.7"),
            move(3, volume="0.7"),
        ],
        limits(volume="1.2"),
        seed=2,
    )

    assert [len(batch.items) for batch in plan.batches] == [1, 1, 1]
    assert all(
        batch.total_volume_m3 <= decimal("1.2")
        for batch in plan.batches
    )


def test_carton_count_limit_splits_batches() -> None:
    plan = plan_move_batches(
        [move(sequence) for sequence in range(1, 6)],
        limits(cartons=2),
        seed=3,
    )

    assert [len(batch.items) for batch in plan.batches] == [2, 2, 1]
    assert all(len(batch.items) <= 2 for batch in plan.batches)
    assert plan.validation_errors == ()


def test_same_sku_and_nearby_move_is_grouped_first() -> None:
    plan = plan_move_batches(
        [
            move(
                1,
                sku="SHARED",
                source_key=(1, 1, 1, 1),
                target_key=(2, 1, 1, 1),
            ),
            move(
                2,
                sku="SHARED",
                source_key=(1, 2, 1, 1),
                target_key=(2, 2, 1, 1),
            ),
            move(
                3,
                sku="SHARED",
                source_key=(9, 9, 1, 1),
                target_key=(9, 9, 1, 1),
            ),
        ],
        limits(cartons=2),
        seed=4,
    )

    assert plan.batches[0].move_sequences == (1, 2)
    assert "same_sku_grouped" in plan.batches[0].reasons


def test_same_seed_produces_identical_batch_plan() -> None:
    moves = [
        move(1, sku="A"),
        move(2, sku="A"),
        move(3, sku="B"),
        move(4, sku="B"),
    ]

    first = plan_move_batches(moves, limits(cartons=2), seed=77)
    second = plan_move_batches(moves, limits(cartons=2), seed=77)

    assert first == second


def test_every_eligible_move_is_batched_exactly_once() -> None:
    moves = [move(sequence) for sequence in range(1, 8)]

    plan = plan_move_batches(moves, limits(cartons=3), seed=5)
    batched_sequences = [
        sequence
        for batch in plan.batches
        for sequence in batch.move_sequences
    ]

    assert sorted(batched_sequences) == list(range(1, 8))
    assert len(batched_sequences) == len(set(batched_sequences))
    assert plan.unbatched_items == ()


def test_single_over_capacity_carton_is_reported_without_invalid_batch() -> None:
    oversized = move(1, weight="300", volume="1.5")

    plan = plan_move_batches(
        [oversized],
        limits(weight="250", volume="1.2"),
        seed=6,
    )

    assert plan.batches == ()
    assert plan.unbatched_items == (oversized,)
    assert {error.code for error in plan.validation_errors} == {
        "max_batch_weight_exceeded",
        "max_batch_volume_exceeded",
    }


def test_blocking_source_move_is_ordered_before_incoming_move() -> None:
    incoming = move(1, source=1, target=2)
    blocking = move(2, source=2, target=3)

    plan = plan_move_batches(
        [incoming, blocking],
        limits(cartons=2),
        seed=7,
    )

    assert plan.batches[0].move_sequences == (2, 1)
    assert "movement_dependencies_ordered" in plan.batches[0].reasons


def test_partial_target_aabb_overlap_creates_physical_dependency() -> None:
    incoming = move(
        1,
        source=1,
        target=2,
        target_placement=placement(1, x="10"),
    )
    blocker = move(
        2,
        source=2,
        target=3,
        source_placement=placement(2, x="20"),
    )

    dependencies = _build_dependencies([incoming, blocker])

    assert dependencies[1] == {2}


def test_non_overlapping_aabbs_in_same_location_do_not_create_dependency() -> None:
    incoming = move(
        1,
        source=1,
        target=2,
        target_placement=placement(1, x="0", width="10"),
    )
    unrelated = move(
        2,
        source=2,
        target=3,
        source_placement=placement(2, x="20", width="10"),
    )

    dependencies = _build_dependencies([incoming, unrelated])

    assert dependencies[1] == set()


def test_upper_source_carton_moves_before_its_support() -> None:
    lower = move(
        1,
        source=1,
        target=3,
        source_placement=placement(1, x="0", z="0", height="10"),
    )
    upper = move(
        2,
        source=1,
        target=4,
        source_placement=placement(2, x="0", z="10", height="10"),
    )

    dependencies = _build_dependencies([lower, upper])

    assert dependencies[1] == {2}


def test_target_support_moves_before_upper_target_carton() -> None:
    lower = move(
        1,
        source=1,
        target=5,
        target_placement=placement(
            1,
            x="0",
            z="0",
            width="20",
            depth="20",
            height="20",
        ),
    )
    upper = move(
        2,
        source=2,
        target=5,
        target_placement=placement(
            2,
            x="0",
            z="20",
            width="20",
            depth="20",
            height="20",
        ),
    )

    dependencies = _build_dependencies([upper, lower])
    plan = plan_move_batches(
        [upper, lower],
        limits(cartons=1),
        seed=9,
    )

    assert dependencies[2] == {1}
    assert [
        batch.move_sequences for batch in plan.batches
    ] == [(1,), (2,)]


def test_dependency_cycle_creates_staging_and_finalize_batches() -> None:
    first = move(1, source=1, target=2)
    second = move(2, source=2, target=1)

    plan = plan_move_batches(
        [first, second],
        limits(cartons=2),
        seed=8,
    )

    assert plan.requires_staging_buffer is True
    assert len(plan.staging_move_sequences) == 1
    staged_sequence = plan.staging_move_sequences[0]
    assert len(plan.batches) == 3
    assert plan.batches[0].requires_staging_buffer is True
    assert "staging_buffer_required" in plan.batches[0].reasons
    assert plan.batches[0].staged_move_sequences == (staged_sequence,)
    assert plan.batches[0].move_sequences == (staged_sequence,)
    assert plan.batches[1].move_sequences == (
        ({1, 2} - {staged_sequence}).pop(),
    )
    assert plan.batches[2].move_sequences == ()
    assert plan.batches[2].finalized_move_sequences == (staged_sequence,)
    logical_sequences = [
        sequence
        for batch in plan.batches
        for sequence in batch.move_sequences
    ]
    assert sorted(logical_sequences) == [1, 2]


def test_staged_target_support_is_finalized_before_upper_move() -> None:
    staged_support = move(
        1,
        source=1,
        target=2,
        source_placement=placement(1, x="0", z="20"),
        target_placement=placement(1, x="0", z="0"),
    )
    cycle_blocker = move(
        2,
        source=2,
        target=1,
        source_placement=placement(2, x="0", z="0"),
        target_placement=placement(2, x="0", z="20"),
    )
    upper = move(
        3,
        source=3,
        target=2,
        source_placement=placement(3, x="0", z="0"),
        target_placement=placement(3, x="0", z="20"),
    )

    plan = plan_move_batches(
        [staged_support, cycle_blocker, upper],
        limits(cartons=1),
        seed=10,
    )

    assert plan.staging_move_sequences == (1,)
    assert [batch.staged_move_sequences for batch in plan.batches] == [
        (1,),
        (),
        (),
        (),
    ]
    assert [batch.move_sequences for batch in plan.batches] == [
        (1,),
        (2,),
        (),
        (3,),
    ]
    assert [batch.finalized_move_sequences for batch in plan.batches] == [
        (),
        (),
        (1,),
        (),
    ]


def test_additional_staging_breaks_source_and_target_support_deadlock() -> None:
    lower_support = move(
        1,
        source=1,
        target=2,
        source_placement=placement(1, x="0", z="20"),
        target_placement=placement(1, x="0", z="0"),
    )
    upper = move(
        2,
        source=2,
        target=2,
        source_placement=placement(2, x="0", z="0"),
        target_placement=placement(2, x="0", z="20"),
    )

    plan = plan_move_batches(
        [lower_support, upper],
        limits(cartons=1),
        seed=11,
    )

    assert plan.requires_staging_buffer is True
    assert plan.staging_move_sequences == (1, 2)
    assert [batch.staged_move_sequences for batch in plan.batches] == [
        (1,),
        (2,),
        (),
        (),
    ]
    assert [batch.finalized_move_sequences for batch in plan.batches] == [
        (),
        (),
        (1,),
        (2,),
    ]
