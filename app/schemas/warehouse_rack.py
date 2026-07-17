"""Warehouse rack detail API response schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class WarehouseRackProductRead(BaseModel):
    id: int
    sku: str
    name: str
    unit_weight_kg: Decimal | None


class WarehouseRackPackagingRead(BaseModel):
    id: int
    units_per_carton: int
    carton_type_code: str


class WarehouseRackCartonRead(BaseModel):
    id: int
    carton_number: str
    status: Literal["available", "reserved", "depleted", "quarantined"]
    capacity_qty: int
    current_qty: int
    reserved_qty: int
    available_qty: int
    expires_at: datetime | None
    product: WarehouseRackProductRead
    packaging: WarehouseRackPackagingRead


class WarehouseRackLocationRead(BaseModel):
    id: int
    aisle: str
    bay: str
    level: str
    slot: str
    is_active: bool
    max_weight_kg: Decimal | None
    used_weight_kg: Decimal | None
    weight_utilization_percent: Decimal | None
    distance_from_dispatch_m: Decimal
    created_at: datetime
    updated_at: datetime
    cartons: list[WarehouseRackCartonRead]


class WarehouseRackSummaryRead(BaseModel):
    """Lightweight occupancy summary for one logical rack."""

    aisle: str = Field(min_length=1, max_length=30)
    bay: str = Field(min_length=1, max_length=30)
    level_count: int = Field(ge=1)
    location_count: int = Field(ge=1)
    active_location_count: int = Field(ge=0)
    carton_count: int = Field(ge=0)
    product_count: int = Field(ge=0)
    total_max_weight_kg: Decimal | None
    total_used_weight_kg: Decimal | None
    weight_utilization_percent: Decimal | None


class WarehouseRackRead(WarehouseRackSummaryRead):
    """Detailed locations that belong to one aisle and bay."""

    locations: list[WarehouseRackLocationRead] = Field(min_length=1)
