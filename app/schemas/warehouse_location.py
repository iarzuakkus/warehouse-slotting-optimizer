"""Depo konumu API istek ve cevap şemaları."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WarehouseLocationBase(BaseModel):
    aisle: str = Field(min_length=1, max_length=30)
    bay: str = Field(min_length=1, max_length=30)
    level: str = Field(min_length=1, max_length=30)
    slot: str = Field(min_length=1, max_length=30)
    max_weight_kg: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=3,
    )
    distance_from_dispatch_m: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=12,
        decimal_places=2,
    )
    is_active: bool = True

    model_config = ConfigDict(str_strip_whitespace=True)


class WarehouseLocationCreate(WarehouseLocationBase):
    """Yeni depo konumu oluştururken kabul edilen alanlar."""


class WarehouseLocationUpdate(BaseModel):
    """Depo konumu güncellerken isteğe bağlı kabul edilen alanlar."""

    aisle: str | None = Field(default=None, min_length=1, max_length=30)
    bay: str | None = Field(default=None, min_length=1, max_length=30)
    level: str | None = Field(default=None, min_length=1, max_length=30)
    slot: str | None = Field(default=None, min_length=1, max_length=30)
    max_weight_kg: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=3,
    )
    distance_from_dispatch_m: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )
    is_active: bool | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> "WarehouseLocationUpdate":
        nullable_fields = {"max_weight_kg"}
        for field in self.model_fields_set:
            if field not in nullable_fields and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class WarehouseLocationRead(WarehouseLocationBase):
    """Veritabanından dönen depo konumu alanları."""

    id: int
    rack_id: int
    usable_width_cm: Decimal
    usable_depth_cm: Decimal
    usable_height_cm: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)
