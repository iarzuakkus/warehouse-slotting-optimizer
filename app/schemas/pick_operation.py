"""Koli üzerinden ürün toplama API şemaları."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PickOperationCreate(BaseModel):
    quantity: int = Field(gt=0)
    operator_reference: str | None = Field(default=None, min_length=1, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)


class PickOperationRead(BaseModel):
    id: int
    allocation_id: int
    location_id: int | None
    quantity: int
    operator_reference: str | None
    picked_at: datetime

    model_config = ConfigDict(from_attributes=True)
