"""Depo yürüyüş grafı route testleri."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes.warehouse_graph import get_warehouse_graph_service
from app.main import app
from app.models.inventory import WarehouseLocation
from app.services.warehouse_graph import WarehouseGraphService


def test_get_route_from_dispatch() -> None:
    location = WarehouseLocation(
        id=42,
        aisle="SYN-A002",
        bay="B003",
        level="L02",
        slot="S02",
        max_weight_kg=1000,
        distance_from_dispatch_m=0,
        is_active=True,
    )
    snapshot = WarehouseGraphService.build_snapshot([location])
    service = SimpleNamespace(load_snapshot=lambda: snapshot)
    app.dependency_overrides[get_warehouse_graph_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.get(
                "/warehouse-graph/routes/from-dispatch/42"
            )
    finally:
        app.dependency_overrides.pop(get_warehouse_graph_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["location_id"] == 42
    assert body["distance_m"] == 51.5
    assert body["nodes"][0] == "dispatch"
    assert body["nodes"][-1] == "location:A002:B003:L02:S02"


def test_route_from_dispatch_rejects_unknown_location() -> None:
    location = WarehouseLocation(
        id=42,
        aisle="SYN-A002",
        bay="B003",
        level="L02",
        slot="S02",
        max_weight_kg=1000,
        distance_from_dispatch_m=0,
        is_active=True,
    )
    snapshot = WarehouseGraphService.build_snapshot([location])
    service = SimpleNamespace(load_snapshot=lambda: snapshot)
    app.dependency_overrides[get_warehouse_graph_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.get(
                "/warehouse-graph/routes/from-dispatch/999"
            )
    finally:
        app.dependency_overrides.pop(get_warehouse_graph_service, None)

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Active warehouse location 999 is not in the graph"
    }


def test_get_route_between_locations() -> None:
    start_location = WarehouseLocation(
        id=42,
        aisle="SYN-A002",
        bay="B001",
        level="L01",
        slot="S02",
        max_weight_kg=1000,
        distance_from_dispatch_m=0,
        is_active=True,
    )
    destination_location = WarehouseLocation(
        id=43,
        aisle="SYN-A001",
        bay="B001",
        level="L01",
        slot="S02",
        max_weight_kg=1000,
        distance_from_dispatch_m=0,
        is_active=True,
    )
    snapshot = WarehouseGraphService.build_snapshot(
        [start_location, destination_location]
    )
    service = SimpleNamespace(load_snapshot=lambda: snapshot)
    app.dependency_overrides[get_warehouse_graph_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.get(
                "/warehouse-graph/routes/between-locations",
                params={
                    "start_location_id": 42,
                    "destination_location_id": 43,
                },
            )
    finally:
        app.dependency_overrides.pop(get_warehouse_graph_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["start_location_id"] == 42
    assert body["destination_location_id"] == 43
    assert body["distance_m"] == 23.0
    assert body["nodes"][0] == "location:A002:B001:L01:S02"
    assert body["nodes"][-1] == "location:A001:B001:L01:S02"


def test_route_between_locations_rejects_unknown_destination() -> None:
    location = WarehouseLocation(
        id=42,
        aisle="SYN-A002",
        bay="B001",
        level="L01",
        slot="S02",
        max_weight_kg=1000,
        distance_from_dispatch_m=0,
        is_active=True,
    )
    snapshot = WarehouseGraphService.build_snapshot([location])
    service = SimpleNamespace(load_snapshot=lambda: snapshot)
    app.dependency_overrides[get_warehouse_graph_service] = lambda: service

    try:
        with TestClient(app) as client:
            response = client.get(
                "/warehouse-graph/routes/between-locations",
                params={
                    "start_location_id": 42,
                    "destination_location_id": 999,
                },
            )
    finally:
        app.dependency_overrides.pop(get_warehouse_graph_service, None)

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Active warehouse location 999 is not in the graph"
    }


def test_get_warehouse_graph_layout() -> None:
    location = WarehouseLocation(
        id=42,
        aisle="SYN-A001",
        bay="B001",
        level="L01",
        slot="S01",
        max_weight_kg=1000,
        distance_from_dispatch_m=0,
        is_active=True,
    )
    snapshot = WarehouseGraphService.build_snapshot([location])
    service = SimpleNamespace(load_snapshot=lambda: snapshot)
    app.dependency_overrides[get_warehouse_graph_service] = lambda: service

    try:
        with TestClient(app) as client:
            topology_response = client.get("/warehouse-graph/layout")
            detailed_response = client.get(
                "/warehouse-graph/layout",
                params={"include_locations": True},
            )
    finally:
        app.dependency_overrides.pop(get_warehouse_graph_service, None)

    assert topology_response.status_code == 200
    assert detailed_response.status_code == 200

    topology = topology_response.json()
    detailed = detailed_response.json()
    assert (topology["node_count"], topology["edge_count"]) == (2, 1)
    assert all(node["node_type"] != "location" for node in topology["nodes"])
    assert (detailed["node_count"], detailed["edge_count"]) == (3, 2)
    location_node = next(
        node for node in detailed["nodes"] if node["node_type"] == "location"
    )
    assert location_node["location_id"] == 42
