"""Veritabanı lokasyonlarını depo yürüyüş grafına bağlayan servis."""

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.algorithms.warehouse_graph import (
    LocationKey,
    ShortestPath,
    WarehouseGraph,
    WarehouseGraphConfig,
    build_regular_warehouse_graph,
)
from app.models.inventory import WarehouseLocation
from app.repositories.warehouse_location import WarehouseLocationRepository
from app.schemas.warehouse_graph import (
    WarehouseGraphEdgeRead,
    WarehouseGraphLayoutRead,
    WarehouseGraphNodeRead,
)


AISLE_PATTERN = re.compile(r"^SYN-A0*([1-9]\d*)$")
BAY_PATTERN = re.compile(r"^B0*([1-9]\d*)$")
LEVEL_PATTERN = re.compile(r"^L0*([1-9]\d*)$")
SLOT_PATTERN = re.compile(r"^S0*([1-9]\d*)$")
PICKUP_NODE_PATTERN = re.compile(
    r"^pickup:A0*([1-9]\d*):B0*([1-9]\d*)$"
)


class WarehouseGraphDataError(Exception):
    """Lokasyon verileri düzenli depo grafına çevrilemediğinde kullanılır."""


class WarehouseGraphLocationNotFoundError(Exception):
    """Lokasyon ID'si etkin graf eşlemesinde bulunamadığında kullanılır."""


@dataclass(frozen=True)
class WarehouseGraphSnapshot:
    """Bir anda yüklenen depo grafı ve veritabanı ID eşlemesi."""

    graph: WarehouseGraph
    location_keys_by_id: dict[int, LocationKey]
    config: WarehouseGraphConfig

    @property
    def location_count(self) -> int:
        return len(self.location_keys_by_id)

    def _location_key(self, location_id: int) -> LocationKey:
        try:
            return self.location_keys_by_id[location_id]
        except KeyError as exc:
            raise WarehouseGraphLocationNotFoundError(
                f"Active warehouse location {location_id} is not in the graph"
            ) from exc

    def path_from_dispatch(self, location_id: int) -> ShortestPath:
        return self.graph.shortest_path_to_location(
            self._location_key(location_id)
        )

    def path_between_locations(
        self,
        start_location_id: int,
        destination_location_id: int,
    ) -> ShortestPath:
        start_key = self._location_key(start_location_id)
        destination_key = self._location_key(destination_location_id)
        return self.graph.shortest_path(
            self.graph.location_node(start_key),
            self.graph.location_node(destination_key),
        )

    def build_layout(
        self,
        include_locations: bool = False,
    ) -> WarehouseGraphLayoutRead:
        """Grafı tarayıcıda çizilebilecek koordinatlı bir yapıya dönüştürür."""
        location_data_by_node = {
            self.graph.location_node(key): (location_id, key)
            for location_id, key in self.location_keys_by_id.items()
        }
        nodes: list[WarehouseGraphNodeRead] = []
        visible_node_ids: set[str] = set()

        for node_id in self.graph.nodes():
            if node_id == "dispatch":
                node = WarehouseGraphNodeRead(
                    id=node_id,
                    node_type="dispatch",
                    label="Sevkiyat",
                    x=-self.config.aisle_spacing_m,
                    y=0.0,
                )
            elif pickup_match := PICKUP_NODE_PATTERN.fullmatch(node_id):
                aisle = int(pickup_match.group(1))
                bay = int(pickup_match.group(2))
                x, y = self._pickup_coordinates(aisle, bay)
                node = WarehouseGraphNodeRead(
                    id=node_id,
                    node_type="pickup",
                    label=f"A{aisle:03d}-B{bay:03d}",
                    x=x,
                    y=y,
                )
            elif node_id in location_data_by_node:
                if not include_locations:
                    continue
                location_id, key = location_data_by_node[node_id]
                pickup_x, pickup_y = self._pickup_coordinates(
                    key.aisle,
                    key.bay,
                )
                slot_step = min(
                    1.0,
                    self.config.aisle_spacing_m
                    / (self.config.slots_per_level + 1),
                )
                level_step = min(
                    0.75,
                    self.config.bay_spacing_m
                    / (self.config.levels_per_bay + 1),
                )
                node = WarehouseGraphNodeRead(
                    id=node_id,
                    node_type="location",
                    label=(
                        f"A{key.aisle:03d}-B{key.bay:03d}-"
                        f"L{key.level:02d}-S{key.slot:02d}"
                    ),
                    x=(
                        pickup_x
                        + (
                            key.slot
                            - (self.config.slots_per_level + 1) / 2
                        )
                        * slot_step
                    ),
                    y=(
                        pickup_y
                        + (
                            key.level
                            - (self.config.levels_per_bay + 1) / 2
                        )
                        * level_step
                    ),
                    location_id=location_id,
                )
            elif node_id.startswith("location:"):
                continue
            else:
                raise WarehouseGraphDataError(
                    f"Unknown warehouse graph node: {node_id}"
                )

            nodes.append(node)
            visible_node_ids.add(node_id)

        edges = [
            WarehouseGraphEdgeRead(
                source=edge.source,
                target=edge.target,
                distance_m=edge.distance_m,
            )
            for edge in self.graph.edges()
            if edge.source in visible_node_ids
            and edge.target in visible_node_ids
        ]
        return WarehouseGraphLayoutRead(
            node_count=len(nodes),
            edge_count=len(edges),
            nodes=nodes,
            edges=edges,
        )

    def _pickup_coordinates(
        self,
        aisle: int,
        bay: int,
    ) -> tuple[float, float]:
        return (
            (aisle - 1) * self.config.aisle_spacing_m,
            bay * self.config.bay_spacing_m,
        )


class WarehouseGraphService:
    def __init__(self, session: Session) -> None:
        self.repository = WarehouseLocationRepository(session)

    def load_snapshot(self) -> WarehouseGraphSnapshot:
        locations = self.repository.list_active_synthetic_locations()
        return self.build_snapshot(locations)

    @staticmethod
    def build_snapshot(
        locations: list[WarehouseLocation],
    ) -> WarehouseGraphSnapshot:
        if not locations:
            raise WarehouseGraphDataError(
                "No active synthetic warehouse locations were found"
            )

        location_keys_by_id: dict[int, LocationKey] = {}
        location_ids_by_key: dict[LocationKey, int] = {}
        for location in locations:
            if location.id is None:
                raise WarehouseGraphDataError(
                    "Warehouse location must have a database ID"
                )
            key = _parse_location_key(location)
            duplicate_id = location_ids_by_key.get(key)
            if duplicate_id is not None:
                raise WarehouseGraphDataError(
                    f"Locations {duplicate_id} and {location.id} map to {key}"
                )
            location_keys_by_id[location.id] = key
            location_ids_by_key[key] = location.id

        config = WarehouseGraphConfig(
            aisle_count=max(key.aisle for key in location_ids_by_key),
            bays_per_aisle=max(key.bay for key in location_ids_by_key),
            levels_per_bay=max(key.level for key in location_ids_by_key),
            slots_per_level=max(key.slot for key in location_ids_by_key),
        )
        graph = build_regular_warehouse_graph(config)
        return WarehouseGraphSnapshot(
            graph=graph,
            location_keys_by_id=location_keys_by_id,
            config=config,
        )


def _parse_coordinate(
    value: str,
    pattern: re.Pattern[str],
    field_name: str,
    location_id: int,
) -> int:
    match = pattern.fullmatch(value)
    if match is None:
        raise WarehouseGraphDataError(
            f"Location {location_id} has invalid {field_name} code: {value}"
        )
    return int(match.group(1))


def _parse_location_key(location: WarehouseLocation) -> LocationKey:
    return LocationKey(
        aisle=_parse_coordinate(
            location.aisle,
            AISLE_PATTERN,
            "aisle",
            location.id,
        ),
        bay=_parse_coordinate(
            location.bay,
            BAY_PATTERN,
            "bay",
            location.id,
        ),
        level=_parse_coordinate(
            location.level,
            LEVEL_PATTERN,
            "level",
            location.id,
        ),
        slot=_parse_coordinate(
            location.slot,
            SLOT_PATTERN,
            "slot",
            location.id,
        ),
    )
