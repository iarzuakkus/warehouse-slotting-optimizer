"""Warehouse rack detail business rules."""

from sqlalchemy.orm import Session

from app.repositories.warehouse_rack import WarehouseRackRepository
from app.schemas.warehouse_rack import WarehouseRackRead


class WarehouseRackNotFoundError(Exception):
    """Raised when an aisle and bay do not contain any locations."""


class WarehouseRackService:
    def __init__(self, session: Session) -> None:
        self.repository = WarehouseRackRepository(session)

    def get_rack(self, aisle: str, bay: str) -> WarehouseRackRead:
        normalized_aisle = aisle.strip().upper()
        normalized_bay = bay.strip().upper()
        locations = self.repository.get_locations(normalized_aisle, normalized_bay)
        if not locations:
            raise WarehouseRackNotFoundError(
                f"Warehouse rack {normalized_aisle}/{normalized_bay} not found"
            )

        return WarehouseRackRead(
            aisle=normalized_aisle,
            bay=normalized_bay,
            location_count=len(locations),
            active_location_count=sum(location.is_active for location in locations),
            locations=locations,
        )
