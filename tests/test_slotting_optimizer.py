"""Deterministic in-memory slotting optimizer tests."""

from copy import deepcopy
from decimal import Decimal

from app.algorithms.carton_placement import (
    CartonDimensions,
    ContainerDimensions,
)
from app.algorithms.slotting_optimizer import (
    SlottingCarton,
    SlottingConfig,
    SlottingLocation,
    SlottingProposal,
    SlottingWeights,
    optimize_slotting,
)


def decimal(value: str) -> Decimal:
    return Decimal(value)


def location(
    location_id: int,
    *,
    aisle_rank: int = 1,
    level_rank: int = 1,
    active: bool = True,
    width: str = "100",
    depth: str = "80",
    height: str = "60",
    max_weight: str | None = "1000",
    dispatch_distance: str = "10",
) -> SlottingLocation:
    return SlottingLocation(
        id=location_id,
        aisle=f"A{aisle_rank:03d}",
        bay="B001",
        level=f"L{level_rank:02d}",
        slot=f"S{location_id:02d}",
        aisle_rank=aisle_rank,
        level_rank=level_rank,
        is_active=active,
        dimensions=ContainerDimensions(
            decimal(width),
            decimal(depth),
            decimal(height),
        ),
        max_weight_kg=(
            decimal(max_weight) if max_weight is not None else None
        ),
        dispatch_distance_m=decimal(dispatch_distance),
    )


def carton(
    carton_id: int,
    *,
    sku: str | None = None,
    weight: str | None = "10",
    length: str = "20",
    width: str = "20",
    height: str = "20",
    current_location_id: int | None = None,
    abc_class: str | None = None,
) -> SlottingCarton:
    positioned = current_location_id is not None
    return SlottingCarton(
        id=carton_id,
        carton_number=f"CARTON-{carton_id:03d}",
        product_id=carton_id,
        sku=sku or f"SKU-{carton_id:03d}",
        dimensions=CartonDimensions(
            decimal(length),
            decimal(width),
            decimal(height),
        ),
        weight_kg=decimal(weight) if weight is not None else None,
        current_location_id=current_location_id,
        current_position_x_cm=decimal("0") if positioned else None,
        current_position_y_cm=decimal("0") if positioned else None,
        current_position_z_cm=decimal("0") if positioned else None,
        current_rotation_degrees=0 if positioned else None,
        abc_class=abc_class,
    )


def only_weight(**changes: str) -> SlottingWeights:
    values = {
        "same_sku_location": decimal("0"),
        "same_rack": decimal("0"),
        "nearby_aisle": decimal("0"),
        "lower_level_for_heavy": decimal("0"),
        "dispatch_distance": decimal("0"),
        "co_shipment_proximity": decimal("0"),
        "location_consolidation": decimal("0"),
        "split_sku": decimal("0"),
        "moves": decimal("0"),
        "volume_utilization": decimal("0"),
    }
    values.update({name: decimal(value) for name, value in changes.items()})
    return SlottingWeights(**values)


def test_same_seed_produces_the_same_result() -> None:
    locations = [location(1), location(2)]
    cartons = [carton(1), carton(2), carton(3)]
    config = SlottingConfig(seed=42)

    first = optimize_slotting(locations, cartons, config)
    second = optimize_slotting(locations, cartons, config)

    assert first == second


def test_optimizer_does_not_mutate_source_inputs() -> None:
    locations = [location(1), location(2)]
    cartons = [carton(1), carton(2)]
    original_locations = deepcopy(locations)
    original_cartons = deepcopy(cartons)

    optimize_slotting(locations, cartons, SlottingConfig(seed=7))

    assert locations == original_locations
    assert cartons == original_cartons


def test_placements_stay_inside_location_bounds_without_overlap() -> None:
    warehouse_locations = [location(1, width="80", depth="40", height="20")]
    cartons = [
        carton(1, length="40", width="40", height="20"),
        carton(2, length="40", width="40", height="20"),
    ]

    result = optimize_slotting(
        warehouse_locations,
        cartons,
        SlottingConfig(seed=1),
    )

    assert result.metrics.unplaced_carton_count == 0
    first, second = result.proposals
    _assert_within_bounds(first, warehouse_locations[0])
    _assert_within_bounds(second, warehouse_locations[0])
    assert not _overlap(first, second, cartons)


def test_weight_capacity_is_never_exceeded() -> None:
    warehouse_locations = [
        location(1, max_weight="100"),
        location(2, max_weight="100"),
    ]
    cartons = [carton(1, weight="60"), carton(2, weight="60")]

    result = optimize_slotting(
        warehouse_locations,
        cartons,
        SlottingConfig(seed=2),
    )

    weights_by_location: dict[int, Decimal] = {}
    for proposal in result.proposals:
        assert proposal.to_location_id is not None
        weights_by_location[proposal.to_location_id] = (
            weights_by_location.get(proposal.to_location_id, Decimal("0"))
            + decimal("60")
        )
    assert all(weight <= decimal("100") for weight in weights_by_location.values())


def test_inactive_location_is_never_selected() -> None:
    result = optimize_slotting(
        [location(1, active=False), location(2, active=True)],
        [carton(1)],
        SlottingConfig(seed=3),
    )

    assert result.proposals[0].to_location_id == 2


def test_same_sku_weight_changes_grouping_result() -> None:
    warehouse_locations = [location(1), location(2)]
    cartons = [
        carton(1, sku="SHARED", current_location_id=1),
        carton(2, sku="SHARED", current_location_id=2),
    ]
    weights = only_weight(same_sku_location="100", moves="10")

    grouped = optimize_slotting(
        warehouse_locations,
        cartons,
        SlottingConfig(seed=4, group_same_sku=True, weights=weights),
    )
    ungrouped = optimize_slotting(
        warehouse_locations,
        cartons,
        SlottingConfig(seed=4, group_same_sku=False, weights=weights),
    )

    assert len(
        {proposal.to_location_id for proposal in grouped.proposals}
    ) == 1
    assert len(
        {proposal.to_location_id for proposal in ungrouped.proposals}
    ) == 2


def test_heavy_carton_is_directed_to_lower_level() -> None:
    weights = only_weight(lower_level_for_heavy="10")
    result = optimize_slotting(
        [location(1, level_rank=1), location(2, level_rank=2)],
        [carton(1, weight="50")],
        SlottingConfig(
            seed=5,
            prefer_lower_levels_for_heavy_cartons=True,
            heavy_carton_threshold_kg=decimal("25"),
            weights=weights,
        ),
    )

    assert result.proposals[0].to_location_id == 1
    assert "heavy_carton_lower_level" in result.proposals[0].reasons


def test_reports_carton_that_cannot_be_placed() -> None:
    result = optimize_slotting(
        [location(1, width="50", depth="50", height="50")],
        [carton(1, length="80", width="60", height="55")],
        SlottingConfig(seed=6),
    )

    proposal = result.proposals[0]
    assert proposal.result_status == "unplaced"
    assert proposal.to_location_id is None
    assert proposal.unplaced_reason == "no_location_satisfies_hard_constraints"
    assert result.metrics.unplaced_carton_count == 1


def test_unknown_weight_is_not_replaced_with_a_fake_value() -> None:
    result = optimize_slotting(
        [location(1)],
        [carton(1, weight=None)],
        SlottingConfig(seed=8),
    )

    assert result.proposals[0].result_status == "unplaced"
    assert result.proposals[0].unplaced_reason == "unknown_carton_weight"


def _assert_within_bounds(
    proposal: SlottingProposal,
    warehouse_location: SlottingLocation,
) -> None:
    assert proposal.proposed_position_x_cm is not None
    assert proposal.proposed_position_y_cm is not None
    assert proposal.proposed_position_z_cm is not None
    width, depth, height = _occupied_dimensions(proposal)
    assert proposal.proposed_position_x_cm + width <= (
        warehouse_location.dimensions.width_cm
    )
    assert proposal.proposed_position_y_cm + depth <= (
        warehouse_location.dimensions.depth_cm
    )
    assert proposal.proposed_position_z_cm + height <= (
        warehouse_location.dimensions.height_cm
    )


def _occupied_dimensions(
    proposal: SlottingProposal,
) -> tuple[Decimal, Decimal, Decimal]:
    dimensions = {
        1: (decimal("40"), decimal("40"), decimal("20")),
        2: (decimal("40"), decimal("40"), decimal("20")),
    }[proposal.carton_id]
    if proposal.proposed_rotation_degrees == 90:
        return dimensions[1], dimensions[0], dimensions[2]
    return dimensions


def _overlap(
    first: SlottingProposal,
    second: SlottingProposal,
    cartons: list[SlottingCarton],
) -> bool:
    dimensions = {item.id: item.dimensions for item in cartons}

    def bounds(
        proposal: SlottingProposal,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
        carton_dimensions = dimensions[proposal.carton_id]
        width = carton_dimensions.length_cm
        depth = carton_dimensions.width_cm
        if proposal.proposed_rotation_degrees == 90:
            width, depth = depth, width
        return (
            proposal.proposed_position_x_cm,
            proposal.proposed_position_x_cm + width,
            proposal.proposed_position_y_cm,
            proposal.proposed_position_y_cm + depth,
            proposal.proposed_position_z_cm,
            proposal.proposed_position_z_cm + carton_dimensions.height_cm,
        )

    first_bounds = bounds(first)
    second_bounds = bounds(second)
    separated = (
        first_bounds[1] <= second_bounds[0]
        or second_bounds[1] <= first_bounds[0]
        or first_bounds[3] <= second_bounds[2]
        or second_bounds[3] <= first_bounds[2]
        or first_bounds[5] <= second_bounds[4]
        or second_bounds[5] <= first_bounds[4]
    )
    return not separated
