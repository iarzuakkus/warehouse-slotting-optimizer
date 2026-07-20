"""Depo konumu iş kuralları ve transaction yönetimi."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.inventory import WarehouseLocation, WarehouseRack
from app.repositories.warehouse_location import WarehouseLocationRepository
from app.repositories.warehouse_rack import WarehouseRackRepository
from app.schemas.warehouse_location import (
    WarehouseLocationCreate,
    WarehouseLocationUpdate,
)


class WarehouseLocationNotFoundError(Exception):
    """İstenen depo konumu bulunamadığında kullanılır."""


class DuplicateWarehouseLocationError(Exception):
    """Aynı fiziksel koordinat tekrar oluşturulmak istendiğinde kullanılır."""


class WarehouseLocationRackNotFoundError(WarehouseLocationNotFoundError):
    """Raised when a location references an undefined physical rack."""


class WarehouseLocationRackCapacityError(Exception):
    """Raised when a location exceeds a physical rack boundary."""


class WarehouseLocationService:
    coordinate_fields = ("aisle", "bay", "level", "slot")

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = WarehouseLocationRepository(session)
        self.rack_repository = WarehouseRackRepository(session)

    def list_locations(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[WarehouseLocation]:
        return self.repository.list_locations(offset=offset, limit=limit)

    def get_location(self, location_id: int) -> WarehouseLocation:
        location = self.repository.get_by_id(location_id)
        if location is None:
            raise WarehouseLocationNotFoundError(
                f"Warehouse location {location_id} not found"
            )
        return location

    def _get_target_rack(self, aisle: str, bay: str) -> WarehouseRack:
        rack = self.rack_repository.get_rack(aisle, bay)
        if rack is None:
            raise WarehouseLocationRackNotFoundError(
                f"Warehouse rack {aisle}/{bay} not found"
            )
        if not rack.is_active:
            raise WarehouseLocationRackCapacityError(
                f"Warehouse rack {aisle}/{bay} is inactive"
            )
        return rack

    @staticmethod
    def _validate_rack_boundary(
        rack: WarehouseRack,
        *,
        level: str,
        slot: str,
        exclude_location_id: int | None = None,
    ) -> None:
        other_locations = [
            location
            for location in rack.locations
            if location.id != exclude_location_id
        ]
        levels = {location.level for location in other_locations}
        levels.add(level)
        if len(levels) > rack.level_count:
            raise WarehouseLocationRackCapacityError(
                f"Warehouse rack {rack.aisle}/{rack.bay} allows "
                f"{rack.level_count} levels"
            )

        slots_on_level = {
            location.slot
            for location in other_locations
            if location.level == level
        }
        slots_on_level.add(slot)
        if len(slots_on_level) > rack.slots_per_level:
            raise WarehouseLocationRackCapacityError(
                f"Warehouse rack {rack.aisle}/{rack.bay} allows "
                f"{rack.slots_per_level} slots per level"
            )

    def create_location(self, data: WarehouseLocationCreate) -> WarehouseLocation:
        normalized_data = data.model_copy(
            update={
                field: getattr(data, field).upper()
                for field in self.coordinate_fields
            }
        )

        existing_location = self.repository.get_by_coordinates(
            **{
                field: getattr(normalized_data, field)
                for field in self.coordinate_fields
            }
        )
        if existing_location is not None:
            raise DuplicateWarehouseLocationError(
                "Warehouse location coordinates already exist"
            )

        rack = self._get_target_rack(
            normalized_data.aisle,
            normalized_data.bay,
        )
        self._validate_rack_boundary(
            rack,
            level=normalized_data.level,
            slot=normalized_data.slot,
        )

        try:
            location = self.repository.create(normalized_data, rack_id=rack.id)
            self.session.commit()
            self.session.refresh(location)
            return location
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateWarehouseLocationError(
                "Warehouse location coordinates already exist"
            ) from exc

    def update_location(
        self,
        location_id: int,
        data: WarehouseLocationUpdate,
    ) -> WarehouseLocation:
        location = self.get_location(location_id)
        normalized_updates = {
            field: getattr(data, field).upper()
            for field in self.coordinate_fields
            if field in data.model_fields_set and getattr(data, field) is not None
        }
        normalized_data = data.model_copy(update=normalized_updates)

        final_coordinates = {
            field: (
                getattr(normalized_data, field)
                if field in normalized_data.model_fields_set
                else getattr(location, field)
            )
            for field in self.coordinate_fields
        }
        existing_location = self.repository.get_by_coordinates(**final_coordinates)
        if existing_location is not None and existing_location.id != location_id:
            raise DuplicateWarehouseLocationError(
                "Warehouse location coordinates already exist"
            )

        rack = self._get_target_rack(
            final_coordinates["aisle"],
            final_coordinates["bay"],
        )
        self._validate_rack_boundary(
            rack,
            level=final_coordinates["level"],
            slot=final_coordinates["slot"],
            exclude_location_id=location_id,
        )

        try:
            location = self.repository.update(
                location,
                normalized_data,
                rack_id=rack.id,
            )
            self.session.commit()
            self.session.refresh(location)
            return location
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateWarehouseLocationError(
                "Warehouse location coordinates already exist"
            ) from exc

    def deactivate_location(self, location_id: int) -> WarehouseLocation:
        location = self.get_location(location_id)
        location = self.repository.deactivate(location)
        self.session.commit()
        self.session.refresh(location)
        return location
