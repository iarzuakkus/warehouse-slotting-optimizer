"""Read-only database queries for logical warehouse racks."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import WarehouseLocation


class WarehouseRackRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_locations(self, aisle: str, bay: str) -> list[WarehouseLocation]:
        statement = (
            select(WarehouseLocation)
            .where(
                WarehouseLocation.aisle == aisle,
                WarehouseLocation.bay == bay,
            )
            .order_by(WarehouseLocation.level, WarehouseLocation.slot)
        )
        return list(self.session.scalars(statement))
