"""Warehouse rack detail API response schemas."""

from pydantic import BaseModel, Field

from app.schemas.warehouse_location import WarehouseLocationRead


class WarehouseRackRead(BaseModel):
    """Locations that belong to one aisle and bay (a logical rack)."""

    aisle: str = Field(min_length=1, max_length=30)
    bay: str = Field(min_length=1, max_length=30)
    location_count: int = Field(ge=1)
    active_location_count: int = Field(ge=0)
    locations: list[WarehouseLocationRead] = Field(min_length=1)
