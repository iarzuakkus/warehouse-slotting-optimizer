"""Veritabanı lokasyonları ile depo grafı eşleme testleri."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.inventory import WarehouseLocation
from app.services.warehouse_graph import (
    WarehouseGraphDataError,
    WarehouseGraphLocationNotFoundError,
    WarehouseGraphService,
)


@pytest.fixture
def graph_session() -> Generator[Session, None, None]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


def warehouse_location(
    location_id: int,
    aisle: int,
    bay: int,
    level: int = 1,
    slot: int = 1,
) -> WarehouseLocation:
    return WarehouseLocation(
        id=location_id,
        aisle=f"SYN-A{aisle:03d}",
        bay=f"B{bay:03d}",
        level=f"L{level:02d}",
        slot=f"S{slot:02d}",
        max_weight_kg=1000,
        distance_from_dispatch_m=0,
        is_active=True,
    )


def test_builds_snapshot_with_database_location_ids() -> None:
    locations = [
        warehouse_location(location_id, aisle, bay)
        for location_id, (aisle, bay) in enumerate(
            (
                (aisle, bay)
                for aisle in range(1, 3)
                for bay in range(1, 4)
            ),
            start=101,
        )
    ]

    snapshot = WarehouseGraphService.build_snapshot(locations)

    assert snapshot.location_count == 6
    assert snapshot.path_from_dispatch(locations[-1].id).distance_m == pytest.approx(
        50.25
    )


def test_calculates_path_between_database_locations() -> None:
    locations = [
        warehouse_location(201, 1, 3),
        warehouse_location(202, 2, 3),
    ]
    snapshot = WarehouseGraphService.build_snapshot(locations)

    path = snapshot.path_between_locations(201, 202)

    assert path.distance_m == pytest.approx(22.5)
    assert "pickup:A001:B003" in path.nodes
    assert "pickup:A002:B003" in path.nodes


def test_rejects_invalid_location_code() -> None:
    location = warehouse_location(301, 1, 1)
    location.level = "GROUND"

    with pytest.raises(WarehouseGraphDataError, match="invalid level code"):
        WarehouseGraphService.build_snapshot([location])


def test_rejects_unknown_or_inactive_location_id() -> None:
    snapshot = WarehouseGraphService.build_snapshot(
        [warehouse_location(401, 1, 1)]
    )

    with pytest.raises(WarehouseGraphLocationNotFoundError, match="402"):
        snapshot.path_from_dispatch(402)


def test_rejects_empty_location_collection() -> None:
    with pytest.raises(WarehouseGraphDataError, match="No active"):
        WarehouseGraphService.build_snapshot([])


def test_loads_only_active_synthetic_locations(
    graph_session: Session,
) -> None:
    active_location = warehouse_location(501, 6, 1)
    active_location.id = None
    inactive_location = warehouse_location(502, 7, 1)
    inactive_location.id = None
    inactive_location.is_active = False
    manual_location = WarehouseLocation(
        aisle="GRAPH-MANUAL",
        bay="B001",
        level="L01",
        slot="S01",
        max_weight_kg=1000,
        distance_from_dispatch_m=0,
        is_active=True,
    )
    graph_session.add_all(
        [active_location, inactive_location, manual_location]
    )
    graph_session.flush()

    snapshot = WarehouseGraphService(graph_session).load_snapshot()

    assert active_location.id in snapshot.location_keys_by_id
    assert inactive_location.id not in snapshot.location_keys_by_id
    assert manual_location.id not in snapshot.location_keys_by_id


def test_builds_topology_and_detailed_layouts() -> None:
    coordinates = (
        (aisle, bay, level, slot)
        for aisle in range(1, 3)
        for bay in range(1, 3)
        for level in range(1, 3)
        for slot in range(1, 3)
    )
    locations = [
        warehouse_location(location_id, aisle, bay, level, slot)
        for location_id, (aisle, bay, level, slot) in enumerate(
            coordinates,
            start=501,
        )
    ]
    snapshot = WarehouseGraphService.build_snapshot(locations)

    topology = snapshot.build_layout()
    detailed = snapshot.build_layout(include_locations=True)
    detailed_locations = [
        node for node in detailed.nodes if node.node_type == "location"
    ]

    assert (topology.node_count, topology.edge_count) == (5, 5)
    assert all(node.node_type != "location" for node in topology.nodes)
    assert (detailed.node_count, detailed.edge_count) == (21, 21)
    assert len(detailed_locations) == 16
    assert {node.location_id for node in detailed_locations} == {
        location.id for location in locations
    }
