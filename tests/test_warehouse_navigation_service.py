"""Database integration tests for physical warehouse navigation."""

from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.inventory import WarehouseLocation
from app.services.warehouse_navigation import (
    WarehouseNavigationLocationNotFoundError,
    WarehouseNavigationService,
)
from tests.factories import create_warehouse_rack


def create_location(
    session: Session,
    *,
    aisle: str,
    bay: str = "B001",
    active: bool = True,
) -> WarehouseLocation:
    rack = create_warehouse_rack(
        session,
        aisle=aisle,
        bay=bay,
    )
    location = WarehouseLocation(
        rack_id=rack.id,
        aisle=rack.aisle,
        bay=rack.bay,
        level="L01",
        slot="S01",
        max_weight_kg=Decimal("1000"),
        distance_from_dispatch_m=Decimal("10"),
        is_active=active,
    )
    session.add(location)
    session.flush()
    return location


def test_loads_rack_dimensions_and_location_approach(
    db_session: Session,
) -> None:
    location = create_location(
        db_session,
        aisle="NAV-SVC-A001",
    )

    snapshot = WarehouseNavigationService(db_session).load_snapshot(
        "forklift"
    )
    route = snapshot.path_from_dispatch(location.id)
    obstacle = next(
        item
        for item in snapshot.navigation.obstacles
        if item.key == (location.aisle, location.bay)
    )

    assert route.nodes[0].id == "dispatch"
    assert route.nodes[-1].id == (
        f"approach:{location.aisle}:{location.bay}:left"
    )
    assert (
        obstacle.physical_bounds.max_x_m
        - obstacle.physical_bounds.min_x_m
    ) == Decimal("0.90")
    assert (
        obstacle.physical_bounds.max_y_m
        - obstacle.physical_bounds.min_y_m
    ) == Decimal("2.15")


def test_dispatch_staging_and_between_location_routes_are_safe(
    db_session: Session,
) -> None:
    first = create_location(
        db_session,
        aisle="NAV-SVC-A002",
        bay="B001",
    )
    second = create_location(
        db_session,
        aisle="NAV-SVC-A003",
        bay="B002",
    )

    snapshot = WarehouseNavigationService(db_session).load_snapshot(
        "pallet_jack"
    )
    routes = [
        snapshot.path_from_dispatch(first.id),
        snapshot.path_between_locations(first.id, second.id),
        snapshot.path_to_staging(second.id),
        snapshot.path_from_staging(second.id),
        snapshot.path_to_dispatch(first.id),
    ]

    for route in routes:
        snapshot.navigation.validate_route(route)


def test_inactive_location_is_not_mapped(
    db_session: Session,
) -> None:
    inactive = create_location(
        db_session,
        aisle="NAV-SVC-INACTIVE",
        active=False,
    )

    snapshot = WarehouseNavigationService(db_session).load_snapshot("cart")

    with pytest.raises(
        WarehouseNavigationLocationNotFoundError,
        match=str(inactive.id),
    ):
        snapshot.path_from_dispatch(inactive.id)


def test_unknown_location_raises_explicit_error(
    db_session: Session,
) -> None:
    create_location(db_session, aisle="NAV-SVC-UNKNOWN")
    snapshot = WarehouseNavigationService(db_session).load_snapshot("cart")

    with pytest.raises(
        WarehouseNavigationLocationNotFoundError,
        match="999999999",
    ):
        snapshot.path_from_dispatch(999999999)


def test_equipment_type_changes_navigation_clearance(
    db_session: Session,
) -> None:
    location = create_location(
        db_session,
        aisle="NAV-SVC-CLEARANCE",
    )
    service = WarehouseNavigationService(db_session)

    cart = service.load_snapshot("cart")
    forklift = service.load_snapshot("forklift")
    cart_approach = cart.path_from_dispatch(location.id).nodes[-1]
    forklift_approach = forklift.path_from_dispatch(location.id).nodes[-1]

    assert (
        cart.navigation.equipment_profile.safety_clearance_m
        == Decimal("0.35")
    )
    assert (
        forklift.navigation.equipment_profile.safety_clearance_m
        == Decimal("0.85")
    )
    assert forklift_approach.x_m < cart_approach.x_m


def test_navigation_repository_uses_constant_query_count(
    db_session: Session,
) -> None:
    create_location(db_session, aisle="NAV-SVC-QUERIES")
    statements: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(
        db_session.bind,
        "before_cursor_execute",
        record_statement,
    )
    try:
        WarehouseNavigationService(db_session).load_snapshot("forklift")
    finally:
        event.remove(
            db_session.bind,
            "before_cursor_execute",
            record_statement,
        )

    select_statements = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(select_statements) == 2
