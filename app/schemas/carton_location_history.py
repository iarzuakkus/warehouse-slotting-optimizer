"""Koli raf hareketi API şemaları."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CartonMovementCreate(BaseModel):
    to_location_id: int | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, min_length=1, max_length=255)

    model_config = ConfigDict(str_strip_whitespace=True)


class CartonLocationHistoryRead(BaseModel):
    id: int
    carton_id: int
    from_location_id: int | None
    to_location_id: int | None
    reason: str | None
    moved_at: datetime

    model_config = ConfigDict(from_attributes=True)
