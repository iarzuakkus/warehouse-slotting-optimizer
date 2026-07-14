"""Fiziksel koli API istek ve cevap şemaları."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


CartonStatus = Literal["available", "reserved", "depleted", "quarantined"]


class CartonCreate(BaseModel):
    carton_number: str = Field(min_length=1, max_length=80)
    product_packaging_id: int = Field(gt=0)
    current_location_id: int | None = Field(default=None, gt=0)
    current_qty: int = Field(ge=0)
    reserved_qty: int = Field(default=0, ge=0)
    status: CartonStatus = "available"
    expires_at: AwareDatetime | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_quantities(self) -> "CartonCreate":
        if self.reserved_qty > self.current_qty:
            raise ValueError("reserved_qty cannot exceed current_qty")
        return self


class CartonUpdate(BaseModel):
    current_qty: int | None = Field(default=None, ge=0)
    reserved_qty: int | None = Field(default=None, ge=0)
    status: CartonStatus | None = None
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_update_fields(self) -> "CartonUpdate":
        nullable_fields = {"expires_at"}
        for field in self.model_fields_set:
            if field not in nullable_fields and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        if (
            "current_qty" in self.model_fields_set
            and "reserved_qty" in self.model_fields_set
            and self.reserved_qty > self.current_qty
        ):
            raise ValueError("reserved_qty cannot exceed current_qty")
        return self


class CartonRead(BaseModel):
    id: int
    carton_number: str
    product_packaging_id: int
    current_location_id: int | None
    capacity_qty: int
    current_qty: int
    reserved_qty: int
    available_qty: int
    status: CartonStatus
    received_at: datetime
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
