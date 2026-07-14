"""Sipariş üst bilgisi API istek ve cevap şemaları."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


OrderStatus = Literal["pending", "allocated", "picking", "completed", "cancelled"]


class OrderCreate(BaseModel):
    order_number: str = Field(min_length=1, max_length=80)
    ordered_at: AwareDatetime | None = None
    due_at: AwareDatetime | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_dates(self) -> "OrderCreate":
        if (
            self.ordered_at is not None
            and self.due_at is not None
            and self.due_at < self.ordered_at
        ):
            raise ValueError("due_at cannot be earlier than ordered_at")
        return self


class OrderUpdate(BaseModel):
    status: OrderStatus | None = None
    due_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def reject_null_status(self) -> "OrderUpdate":
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


class OrderRead(BaseModel):
    id: int
    order_number: str
    status: OrderStatus
    ordered_at: datetime
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
