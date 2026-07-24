"""Tests for obstacle-aware physical warehouse navigation."""

from decimal import Decimal

import pytest

from app.algorithms.warehouse_navigation import (
    EQUIPMENT_NAVIGATION_PROFILES,
    PhysicalRack,
    WarehouseNavigationConfig,
    WarehouseNavigationConfigurationError,
    WarehouseNavigationRouteError,
    build_warehouse_navigation,
)


def rack(aisle: str, bay: str) -> PhysicalRack:
    return PhysicalRack(
        aisle=aisle,
        bay=bay,
        width_m=Decimal("2.15"),
        depth_m=Decimal("0.90"),
    )


def rack_grid() -> list[PhysicalRack]:
    return [
        rack(aisle, bay)
        for aisle in ("SYN-A001", "SYN-A002")
        for bay in ("B001", "B002")
    ]


def test_route_segments_do_not_intersect_expanded_rack_obstacles() -> None:
    snapshot = build_warehouse_navigation(
        rack_grid(),
        equipment_type="forklift",
    )

    routes = [
        snapshot.path_from_dispatch("SYN-A001", "B001"),
        snapshot.path_between_racks(
            "SYN-A001",
            "B001",
            "SYN-A002",
            "B002",
        ),
        snapshot.path_to_staging("SYN-A002", "B002"),
    ]

    for route in routes:
        snapshot.validate_route(route)
        assert all(
            snapshot.segment_is_safe(start, end)
            for start, end in zip(route.nodes, route.nodes[1:])
        )


def test_equipment_types_use_distinct_safety_margins() -> None:
    margins = {
        equipment_type: profile.obstacle_margin_m
        for equipment_type, profile in (
            EQUIPMENT_NAVIGATION_PROFILES.items()
        )
    }

    assert margins == {
        "cart": Decimal("0.675"),
        "pallet_jack": Decimal("0.95"),
        "forklift": Decimal("1.45"),
    }

    cart = build_warehouse_navigation(
        [rack("SYN-A001", "B001")],
        equipment_type="cart",
    )
    forklift = build_warehouse_navigation(
        [rack("SYN-A001", "B001")],
        equipment_type="forklift",
    )
    cart_approach = cart.path_from_dispatch(
        "SYN-A001", "B001"
    ).nodes[-1]
    forklift_approach = forklift.path_from_dispatch(
        "SYN-A001", "B001"
    ).nodes[-1]

    assert forklift_approach.x_m < cart_approach.x_m


def test_same_input_produces_identical_navigation_route() -> None:
    first = build_warehouse_navigation(
        rack_grid(),
        equipment_type="forklift",
    )
    second = build_warehouse_navigation(
        list(reversed(rack_grid())),
        equipment_type="forklift",
    )

    assert first.path_from_dispatch(
        "SYN-A002", "B002"
    ) == second.path_from_dispatch("SYN-A002", "B002")


def test_dispatch_route_ends_at_correct_safe_approach() -> None:
    snapshot = build_warehouse_navigation(
        rack_grid(),
        equipment_type="forklift",
    )

    route = snapshot.path_from_dispatch("SYN-A002", "B002")

    assert route.nodes[0].id == "dispatch"
    assert route.nodes[-1].id == "approach:SYN-A002:B002:left"
    assert route.nodes[-1].type == "approach"
    obstacle = next(
        item
        for item in snapshot.obstacles
        if item.key == ("SYN-A002", "B002")
    )
    assert route.nodes[-1].x_m < obstacle.blocked_bounds.min_x_m


def test_route_between_aisles_uses_cross_aisle() -> None:
    snapshot = build_warehouse_navigation(
        rack_grid(),
        equipment_type="forklift",
    )

    route = snapshot.path_between_racks(
        "SYN-A001",
        "B002",
        "SYN-A002",
        "B002",
    )

    assert any(node.type == "cross_aisle" for node in route.nodes)
    assert route.nodes[0].id == "approach:SYN-A001:B002:left"
    assert route.nodes[-1].id == "approach:SYN-A002:B002:left"


def test_staging_route_is_safe_and_starts_at_staging() -> None:
    snapshot = build_warehouse_navigation(
        rack_grid(),
        equipment_type="pallet_jack",
    )

    route = snapshot.path_from_staging("SYN-A001", "B002")

    assert route.nodes[0].id == "staging"
    assert route.nodes[-1].id == "approach:SYN-A001:B002:left"
    snapshot.validate_route(route)


def test_all_navigation_nodes_remain_inside_warehouse_bounds() -> None:
    snapshot = build_warehouse_navigation(
        rack_grid(),
        equipment_type="forklift",
    )

    assert all(
        snapshot.warehouse_bounds.contains(node.x_m, node.y_m)
        for node in snapshot.nodes_by_id.values()
    )


def test_rejects_aisle_that_is_too_narrow_for_forklift() -> None:
    with pytest.raises(
        WarehouseNavigationConfigurationError,
        match="insufficient for forklift",
    ):
        build_warehouse_navigation(
            rack_grid(),
            equipment_type="forklift",
            config=WarehouseNavigationConfig(
                drive_aisle_width_m=Decimal("2.90")
            ),
        )


def test_unreachable_approach_raises_explicit_route_error() -> None:
    snapshot = build_warehouse_navigation(
        [rack("SYN-A001", "B001")],
        equipment_type="cart",
    )
    approach_id = "approach:SYN-A001:B001:left"
    aisle_id = "aisle:SYN-A001:B001"
    snapshot._adjacency[approach_id].clear()
    snapshot._adjacency[aisle_id].pop(approach_id)

    with pytest.raises(
        WarehouseNavigationRouteError,
        match="No safe navigation route",
    ):
        snapshot.path_from_dispatch("SYN-A001", "B001")


def test_route_distance_matches_segment_distance_sum() -> None:
    snapshot = build_warehouse_navigation(
        rack_grid(),
        equipment_type="forklift",
    )

    route = snapshot.path_from_dispatch("SYN-A002", "B002")
    segment_total = sum(
        (
            snapshot.edge_distance(start.id, end.id)
            for start, end in zip(route.nodes, route.nodes[1:])
        ),
        start=Decimal("0"),
    )

    assert route.distance_m == segment_total
