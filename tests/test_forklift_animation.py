"""Unit tests for deterministic material-handling animation timelines."""

from decimal import Decimal

import pytest

from app.algorithms.forklift_animation import (
    AnimationRouteLeg,
    AnimationRoutePoint,
    AnimationStop,
    build_batch_animation,
)


def point(
    node_id: str,
    *,
    x: str,
    y: str = "0",
    distance: str = "0",
) -> AnimationRoutePoint:
    return AnimationRoutePoint(
        node_id=node_id,
        x_m=Decimal(x),
        y_m=Decimal(y),
        distance_from_previous_m=Decimal(distance),
    )


def leg(
    start: str,
    end: str,
    *,
    start_x: str,
    end_x: str,
    distance: str,
) -> AnimationRouteLeg:
    return AnimationRouteLeg(
        points=(
            point(start, x=start_x),
            point(end, x=end_x, distance=distance),
        )
    )


def test_builds_dispatch_pickup_dropoff_and_return_timeline() -> None:
    timeline = build_batch_animation(
        equipment_type="forklift",
        stops=[
            AnimationStop(
                type="pickup",
                location_id=10,
                carton_ids=(101,),
                route_from_previous=leg(
                    "dispatch",
                    "pickup:A001:B001",
                    start_x="0",
                    end_x="10",
                    distance="10",
                ),
            ),
            AnimationStop(
                type="dropoff",
                location_id=20,
                carton_ids=(101,),
                route_from_previous=leg(
                    "pickup:A001:B001",
                    "pickup:A002:B001",
                    start_x="10",
                    end_x="30",
                    distance="20",
                ),
            ),
        ],
        return_to_dispatch=leg(
            "pickup:A002:B001",
            "dispatch",
            start_x="30",
            end_x="0",
            distance="30",
        ),
    )

    assert [event.type for event in timeline.events] == [
        "travel",
        "pickup",
        "travel",
        "dropoff",
        "travel",
    ]
    assert timeline.route_distance_m == Decimal("60.00")
    assert timeline.estimated_duration_seconds == Decimal("40.00")
    assert timeline.events[0].carton_ids == ()
    assert timeline.events[2].carton_ids == (101,)
    assert timeline.events[4].carton_ids == ()


def test_waypoints_have_cumulative_distance_and_time() -> None:
    timeline = build_batch_animation(
        equipment_type="forklift",
        stops=[
            AnimationStop(
                type="pickup",
                location_id=10,
                carton_ids=(101,),
                route_from_previous=AnimationRouteLeg(
                    points=(
                        point("dispatch", x="0"),
                        point("crossing", x="5", distance="5"),
                        point(
                            "pickup:A001:B001",
                            x="12",
                            distance="7",
                        ),
                    )
                ),
            )
        ],
        return_to_dispatch=leg(
            "pickup:A001:B001",
            "dispatch",
            start_x="12",
            end_x="0",
            distance="12",
        ),
    )

    outbound = timeline.events[0]
    assert [
        waypoint.cumulative_distance_m
        for waypoint in outbound.waypoints
    ] == [
        Decimal("0.00"),
        Decimal("5.00"),
        Decimal("12.00"),
    ]
    assert [
        waypoint.elapsed_seconds for waypoint in outbound.waypoints
    ] == [
        Decimal("0.00"),
        Decimal("2.00"),
        Decimal("4.80"),
    ]


def test_same_input_produces_identical_timeline() -> None:
    stop = AnimationStop(
        type="pickup",
        location_id=10,
        carton_ids=(101, 102),
        route_from_previous=leg(
            "dispatch",
            "pickup:A001:B001",
            start_x="0",
            end_x="10",
            distance="10",
        ),
    )
    return_leg = leg(
        "pickup:A001:B001",
        "dispatch",
        start_x="10",
        end_x="0",
        distance="10",
    )

    first = build_batch_animation(
        equipment_type="forklift",
        stops=[stop],
        return_to_dispatch=return_leg,
    )
    second = build_batch_animation(
        equipment_type="forklift",
        stops=[stop],
        return_to_dispatch=return_leg,
    )

    assert first == second


def test_equipment_speed_changes_travel_duration() -> None:
    stop = AnimationStop(
        type="pickup",
        location_id=10,
        carton_ids=(101,),
        route_from_previous=leg(
            "dispatch",
            "pickup:A001:B001",
            start_x="0",
            end_x="14",
            distance="14",
        ),
    )
    return_leg = leg(
        "pickup:A001:B001",
        "dispatch",
        start_x="14",
        end_x="0",
        distance="14",
    )

    cart = build_batch_animation(
        equipment_type="cart",
        stops=[stop],
        return_to_dispatch=return_leg,
    )
    forklift = build_batch_animation(
        equipment_type="forklift",
        stops=[stop],
        return_to_dispatch=return_leg,
    )

    assert forklift.estimated_duration_seconds < (
        cart.estimated_duration_seconds
    )


def test_staging_event_and_loaded_return_are_preserved() -> None:
    timeline = build_batch_animation(
        equipment_type="forklift",
        stops=[
            AnimationStop(
                type="staging_pickup",
                location_id=10,
                carton_ids=(101,),
                route_from_previous=leg(
                    "dispatch",
                    "pickup:A001:B001",
                    start_x="0",
                    end_x="10",
                    distance="10",
                ),
            )
        ],
        return_to_dispatch=leg(
            "pickup:A001:B001",
            "dispatch",
            start_x="10",
            end_x="0",
            distance="10",
        ),
    )

    assert timeline.events[1].type == "staging_pickup"
    assert timeline.events[-1].type == "travel"
    assert timeline.events[-1].carton_ids == (101,)


def test_staging_finalization_starts_loaded_and_returns_empty() -> None:
    timeline = build_batch_animation(
        equipment_type="forklift",
        stops=[
            AnimationStop(
                type="staging_dropoff",
                location_id=10,
                carton_ids=(101,),
                route_from_previous=leg(
                    "dispatch",
                    "pickup:A001:B001",
                    start_x="0",
                    end_x="10",
                    distance="10",
                ),
            )
        ],
        return_to_dispatch=leg(
            "pickup:A001:B001",
            "dispatch",
            start_x="10",
            end_x="0",
            distance="10",
        ),
        initial_loaded_carton_ids=(101,),
    )

    assert timeline.events[0].type == "travel"
    assert timeline.events[0].carton_ids == (101,)
    assert timeline.events[1].type == "staging_dropoff"
    assert timeline.events[-1].type == "travel"
    assert timeline.events[-1].carton_ids == ()


def test_rejects_invalid_initial_load() -> None:
    stop = AnimationStop(
        type="staging_dropoff",
        location_id=10,
        carton_ids=(101,),
        route_from_previous=leg(
            "dispatch",
            "pickup:A001:B001",
            start_x="0",
            end_x="10",
            distance="10",
        ),
    )
    return_leg = leg(
        "pickup:A001:B001",
        "dispatch",
        start_x="10",
        end_x="0",
        distance="10",
    )

    with pytest.raises(ValueError, match="must be positive"):
        build_batch_animation(
            equipment_type="forklift",
            stops=[stop],
            return_to_dispatch=return_leg,
            initial_loaded_carton_ids=(0,),
        )
    with pytest.raises(ValueError, match="must be unique"):
        build_batch_animation(
            equipment_type="forklift",
            stops=[stop],
            return_to_dispatch=return_leg,
            initial_loaded_carton_ids=(101, 101),
        )


def test_rejects_empty_stops_and_invalid_route_distance() -> None:
    return_leg = AnimationRouteLeg(
        points=(point("dispatch", x="0"),)
    )

    with pytest.raises(
        ValueError,
        match="must contain at least one stop",
    ):
        build_batch_animation(
            equipment_type="forklift",
            stops=[],
            return_to_dispatch=return_leg,
        )

    with pytest.raises(
        ValueError,
        match="distance cannot be negative",
    ):
        point("invalid", x="0", distance="-1")
