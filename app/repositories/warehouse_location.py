"""Depo konumu tablosu için SQLAlchemy veritabanı işlemleri."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import WarehouseLocation
from app.schemas.warehouse_location import (
    WarehouseLocationCreate,
    WarehouseLocationUpdate,
)


class WarehouseLocationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, location_id: int) -> WarehouseLocation | None:
        return self.session.get(WarehouseLocation, location_id)

    def get_by_coordinates(
        self,
        aisle: str,
        bay: str,
        level: str,
        slot: str,
    ) -> WarehouseLocation | None:
        statement = select(WarehouseLocation).where(
            WarehouseLocation.aisle == aisle,
            WarehouseLocation.bay == bay,
            WarehouseLocation.level == level,
            WarehouseLocation.slot == slot,
        )
        return self.session.scalar(statement)

    def list_locations(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[WarehouseLocation]:
        statement = (
            select(WarehouseLocation)
            .order_by(
                WarehouseLocation.aisle,
                WarehouseLocation.bay,
                WarehouseLocation.level,
                WarehouseLocation.slot,
            )
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def list_active_synthetic_locations(self) -> list[WarehouseLocation]:
        statement = (
            select(WarehouseLocation)
            .where(
                WarehouseLocation.is_active.is_(True),
                WarehouseLocation.aisle.like("SYN-A%"),
            )
            .order_by(
                WarehouseLocation.aisle,
                WarehouseLocation.bay,
                WarehouseLocation.level,
                WarehouseLocation.slot,
            )
        )
        return list(self.session.scalars(statement))

    def create(self, data: WarehouseLocationCreate) -> WarehouseLocation:
        location = WarehouseLocation(**data.model_dump())
        self.session.add(location)
        self.session.flush()
        return location

    def update(
        self,
        location: WarehouseLocation,
        data: WarehouseLocationUpdate,
    ) -> WarehouseLocation:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(location, field, value)

        self.session.flush()
        return location

    def deactivate(self, location: WarehouseLocation) -> WarehouseLocation:
        location.is_active = False
        self.session.flush()
        return location
