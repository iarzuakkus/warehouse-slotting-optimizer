"""Koli ayırma API istek ve cevap şemaları."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CartonAllocationStatus = Literal["allocated", "picking", "picked", "cancelled"]


class CartonAllocationCreate(BaseModel):
    carton_id: int = Field(gt=0)
    allocated_qty: int = Field(gt=0)


class CartonAllocationUpdate(BaseModel):
    allocated_qty: int | None = Field(default=None, gt=0)
    status: Literal["allocated", "cancelled"] | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "CartonAllocationUpdate":
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class CartonAllocationRead(BaseModel):
    id: int
    order_line_id: int
    carton_id: int
    allocated_qty: int
    picked_qty: int
    status: CartonAllocationStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
