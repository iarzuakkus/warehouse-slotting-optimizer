"""Sipariş satırı API istek ve cevap şemaları."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderLineCreate(BaseModel):
    product_id: int = Field(gt=0)
    ordered_qty: int = Field(gt=0)


class OrderLineUpdate(BaseModel):
    ordered_qty: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def reject_explicit_null(self) -> "OrderLineUpdate":
        if "ordered_qty" in self.model_fields_set and self.ordered_qty is None:
            raise ValueError("ordered_qty cannot be null")
        return self


class OrderLineRead(BaseModel):
    id: int
    order_id: int
    product_id: int
    ordered_qty: int
    fulfilled_qty: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
