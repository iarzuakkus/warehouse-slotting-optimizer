"""Database-backed physical navigation for warehouse equipment."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.algorithms.warehouse_navigation import (
    EquipmentType,
    NavigationRoute,
    PhysicalRack,
    WarehouseNavigationConfig,
    WarehouseNavigationSnapshot,
    build_warehouse_navigation,
)
from app.repositories.warehouse_rack import WarehouseRackRepository


CENTIMETERS_PER_METER = Decimal("100")


class WarehouseNavigationDataError(Exception):
    """Raised when physical rack data cannot build a navigation layout."""


class WarehouseNavigationLocationNotFoundError(Exception):
    """Raised when an active location has no navigation approach."""


@dataclass(frozen=True)
class PhysicalWarehouseNavigationSnapshot:
    """Safe navigation graph plus database location-to-rack mapping."""

    navigation: WarehouseNavigationSnapshot
    rack_key_by_location_id: dict[int, tuple[str, str]]

    def path_from_dispatch(self, location_id: int) -> NavigationRoute:
        aisle, bay = self._rack_key(location_id)
        return self.navigation.path_from_dispatch(aisle, bay)

    def path_between_locations(
        self,
        start_location_id: int,
        destination_location_id: int,
    ) -> NavigationRoute:
        start_aisle, start_bay = self._rack_key(start_location_id)
        destination_aisle, destination_bay = self._rack_key(
            destination_location_id
        )
        return self.navigation.path_between_racks(
            start_aisle,
            start_bay,
            destination_aisle,
            destination_bay,
        )

    def path_to_dispatch(self, location_id: int) -> NavigationRoute:
        aisle, bay = self._rack_key(location_id)
        return self.navigation.path_to_dispatch(aisle, bay)

    def path_from_staging(self, location_id: int) -> NavigationRoute:
        aisle, bay = self._rack_key(location_id)
        return self.navigation.path_from_staging(aisle, bay)

    def path_to_staging(self, location_id: int) -> NavigationRoute:
        aisle, bay = self._rack_key(location_id)
        return self.navigation.path_to_staging(aisle, bay)

    def _rack_key(self, location_id: int) -> tuple[str, str]:
        try:
            return self.rack_key_by_location_id[location_id]
        except KeyError as exc:
            raise WarehouseNavigationLocationNotFoundError(
                f"Active warehouse location {location_id} has no "
                "physical navigation approach"
            ) from exc


class WarehouseNavigationService:
    def __init__(self, session: Session) -> None:
        self.repository = WarehouseRackRepository(session)

    def load_snapshot(
        self,
        equipment_type: EquipmentType,
        config: WarehouseNavigationConfig | None = None,
    ) -> PhysicalWarehouseNavigationSnapshot:
        racks = self.repository.list_active_racks_for_navigation()
        if not racks:
            raise WarehouseNavigationDataError(
                "No active physical warehouse racks were found"
            )

        physical_racks = [
            PhysicalRack(
                aisle=rack.aisle,
                bay=rack.bay,
                width_m=rack.width_cm / CENTIMETERS_PER_METER,
                depth_m=rack.depth_cm / CENTIMETERS_PER_METER,
            )
            for rack in racks
        ]
        rack_key_by_location_id = {
            location.id: (rack.aisle, rack.bay)
            for rack in racks
            for location in rack.locations
            if location.id is not None
        }
        if not rack_key_by_location_id:
            raise WarehouseNavigationDataError(
                "No active warehouse locations were found for navigation"
            )

        return PhysicalWarehouseNavigationSnapshot(
            navigation=build_warehouse_navigation(
                physical_racks,
                equipment_type=equipment_type,
                config=config,
            ),
            rack_key_by_location_id=rack_key_by_location_id,
        )
