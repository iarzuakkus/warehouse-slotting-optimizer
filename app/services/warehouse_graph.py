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


AISLE_PATTERN = re.compile(r"^SYN-A0*([1-9]\d*)$")
BAY_PATTERN = re.compile(r"^B0*([1-9]\d*)$")
LEVEL_PATTERN = re.compile(r"^L0*([1-9]\d*)$")
SLOT_PATTERN = re.compile(r"^S0*([1-9]\d*)$")


class WarehouseGraphDataError(Exception):
    """Lokasyon verileri düzenli depo grafına çevrilemediğinde kullanılır."""


class WarehouseGraphLocationNotFoundError(Exception):
    """Lokasyon ID'si etkin graf eşlemesinde bulunamadığında kullanılır."""


@dataclass(frozen=True)
class WarehouseGraphSnapshot:
    """Bir anda yüklenen depo grafı ve veritabanı ID eşlemesi."""

    graph: WarehouseGraph
    location_keys_by_id: dict[int, LocationKey]

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
