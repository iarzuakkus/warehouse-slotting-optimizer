"""Deterministic physical carton placement algorithm tests."""

from decimal import Decimal

import pytest

from app.algorithms.carton_placement import (
    CartonDimensions,
    ContainerDimensions,
    PlacedCarton,
    find_placement,
    has_weight_capacity,
    volume_utilization_percent,
)


def decimal(value: str) -> Decimal:
    return Decimal(value)


def test_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValueError, match="Container dimensions must be positive"):
        ContainerDimensions(decimal("0"), decimal("80"), decimal("60"))

    with pytest.raises(ValueError, match="Carton dimensions must be positive"):
        CartonDimensions(decimal("40"), decimal("-1"), decimal("20"))


def test_weight_capacity_is_checked_separately() -> None:
    assert has_weight_capacity(
        decimal("900"), decimal("100"), decimal("1000")
    )
    assert not has_weight_capacity(
        decimal("900"), decimal("100.001"), decimal("1000")
    )
    assert not has_weight_capacity(None, decimal("10"), decimal("1000"))
    assert not has_weight_capacity(decimal("10"), None, decimal("1000"))
    assert not has_weight_capacity(decimal("10"), decimal("10"), None)


def test_rejects_carton_that_exceeds_physical_bounds() -> None:
    result = find_placement(
        ContainerDimensions(decimal("50"), decimal("50"), decimal("50")),
        CartonDimensions(decimal("60"), decimal("55"), decimal("10")),
        [],
    )

    assert result is None


def test_places_cartons_left_to_right_without_overlap() -> None:
    container = ContainerDimensions(decimal("100"), decimal("80"), decimal("60"))
    dimensions = CartonDimensions(decimal("40"), decimal("30"), decimal("20"))
    first = find_placement(container, dimensions, [])
    assert first is not None

    second = find_placement(
        container,
        dimensions,
        [first.to_placed_carton(carton_id=1)],
    )

    assert first.position_x_cm == 0
    assert second is not None
    assert second.position_x_cm == decimal("40")
    assert second.position_y_cm == 0
    assert second.position_z_cm == 0


def test_rotates_carton_when_normal_orientation_does_not_fit() -> None:
    result = find_placement(
        ContainerDimensions(decimal("50"), decimal("100"), decimal("60")),
        CartonDimensions(decimal("80"), decimal("40"), decimal("50")),
        [],
    )

    assert result is not None
    assert result.rotation_degrees == 90
    assert result.occupied_width_cm == decimal("40")
    assert result.occupied_depth_cm == decimal("80")


def test_stacks_carton_after_floor_is_full() -> None:
    container = ContainerDimensions(decimal("40"), decimal("30"), decimal("40"))
    dimensions = CartonDimensions(decimal("40"), decimal("30"), decimal("20"))
    first = find_placement(container, dimensions, [])
    assert first is not None

    second = find_placement(
        container,
        dimensions,
        [first.to_placed_carton(carton_id=1)],
    )

    assert second is not None
    assert second.position_x_cm == 0
    assert second.position_y_cm == 0
    assert second.position_z_cm == decimal("20")


def test_rejects_stack_without_full_support() -> None:
    partial_support = PlacedCarton(
        carton_id=1,
        position_x_cm=decimal("0"),
        position_y_cm=decimal("0"),
        position_z_cm=decimal("0"),
        occupied_width_cm=decimal("20"),
        occupied_depth_cm=decimal("20"),
        occupied_height_cm=decimal("20"),
        rotation_degrees=0,
    )

    result = find_placement(
        ContainerDimensions(decimal("40"), decimal("40"), decimal("40")),
        CartonDimensions(decimal("40"), decimal("40"), decimal("20")),
        [partial_support],
    )

    assert result is None


def test_returns_none_when_no_space_remains() -> None:
    full_location = PlacedCarton(
        carton_id=1,
        position_x_cm=decimal("0"),
        position_y_cm=decimal("0"),
        position_z_cm=decimal("0"),
        occupied_width_cm=decimal("100"),
        occupied_depth_cm=decimal("80"),
        occupied_height_cm=decimal("60"),
        rotation_degrees=0,
    )

    result = find_placement(
        ContainerDimensions(decimal("100"), decimal("80"), decimal("60")),
        CartonDimensions(decimal("10"), decimal("10"), decimal("10")),
        [full_location],
    )

    assert result is None


def test_calculates_volume_utilization_percent() -> None:
    placed = PlacedCarton(
        carton_id=1,
        position_x_cm=decimal("0"),
        position_y_cm=decimal("0"),
        position_z_cm=decimal("0"),
        occupied_width_cm=decimal("50"),
        occupied_depth_cm=decimal("50"),
        occupied_height_cm=decimal("50"),
        rotation_degrees=0,
    )

    utilization = volume_utilization_percent(
        ContainerDimensions(decimal("100"), decimal("100"), decimal("100")),
        [placed],
    )

    assert utilization == decimal("12.50")


def test_same_input_produces_same_placement() -> None:
    container = ContainerDimensions(decimal("100"), decimal("80"), decimal("60"))
    dimensions = CartonDimensions(decimal("40"), decimal("30"), decimal("20"))
    occupied = [
        PlacedCarton(
            carton_id=1,
            position_x_cm=decimal("0"),
            position_y_cm=decimal("0"),
            position_z_cm=decimal("0"),
            occupied_width_cm=decimal("40"),
            occupied_depth_cm=decimal("30"),
            occupied_height_cm=decimal("20"),
            rotation_degrees=0,
        )
    ]

    first_result = find_placement(container, dimensions, occupied)
    second_result = find_placement(container, dimensions, occupied)

    assert first_result == second_result
