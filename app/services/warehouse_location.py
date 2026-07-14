"""Depo konumu iş kuralları ve transaction yönetimi."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.inventory import WarehouseLocation
from app.repositories.warehouse_location import WarehouseLocationRepository
from app.schemas.warehouse_location import (
    WarehouseLocationCreate,
    WarehouseLocationUpdate,
)


class WarehouseLocationNotFoundError(Exception):
    """İstenen depo konumu bulunamadığında kullanılır."""


class DuplicateWarehouseLocationError(Exception):
    """Aynı fiziksel koordinat tekrar oluşturulmak istendiğinde kullanılır."""


class WarehouseLocationService:
    coordinate_fields = ("aisle", "bay", "level", "slot")

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = WarehouseLocationRepository(session)

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

        try:
            location = self.repository.create(normalized_data)
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

        try:
            location = self.repository.update(location, normalized_data)
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
