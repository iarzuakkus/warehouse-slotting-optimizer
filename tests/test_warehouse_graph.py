"""Düzenli depo grafı ve en kısa yol testleri."""

import pytest

from app.algorithms.warehouse_graph import (
    DISPATCH_NODE,
    LocationKey,
    WarehouseGraph,
    WarehouseGraphConfig,
    build_regular_warehouse_graph,
)


@pytest.fixture
def smoke_graph() -> WarehouseGraph:
    return build_regular_warehouse_graph(
        WarehouseGraphConfig(
            aisle_count=5,
            bays_per_aisle=5,
            levels_per_bay=2,
            slots_per_level=2,
        )
    )


def test_builds_nodes_for_smoke_profile(smoke_graph: WarehouseGraph) -> None:
    assert smoke_graph.location_count == 100
    assert smoke_graph.node_count == 126


def test_dispatch_distance_matches_synthetic_distance_formula(
    smoke_graph: WarehouseGraph,
) -> None:
    path = smoke_graph.shortest_path_to_location(LocationKey(2, 3, 2, 2))

    assert path.distance_m == pytest.approx(51.5)
    assert path.nodes[0] == DISPATCH_NODE
    assert path.nodes[-1] == "location:A002:B003:L02:S02"


def test_rear_cross_aisle_shortens_route_between_rear_locations(
    smoke_graph: WarehouseGraph,
) -> None:
    start = smoke_graph.location_node(LocationKey(1, 5, 1, 1))
    destination = smoke_graph.location_node(LocationKey(2, 5, 1, 1))

    path = smoke_graph.shortest_path(start, destination)

    assert path.distance_m == pytest.approx(22.5)
    assert "pickup:A001:B005" in path.nodes
    assert "pickup:A002:B005" in path.nodes


def test_rejects_unknown_location(smoke_graph: WarehouseGraph) -> None:
    with pytest.raises(ValueError, match="Unknown warehouse location"):
        smoke_graph.shortest_path_to_location(LocationKey(6, 1, 1, 1))


def test_rejects_invalid_graph_dimensions() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        WarehouseGraphConfig(
            aisle_count=0,
            bays_per_aisle=5,
            levels_per_bay=2,
            slots_per_level=2,
        )
