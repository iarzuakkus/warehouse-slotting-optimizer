"""Optimizasyon çalışması API şemaları."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


OptimizationRunStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
]


class OptimizationRunCreate(BaseModel):
    algorithm_name: str = Field(min_length=1, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(str_strip_whitespace=True)


class OptimizationRunUpdate(BaseModel):
    status: Literal["running", "completed", "failed", "cancelled"] | None = None
    objective_value: Decimal | None = Field(
        default=None,
        max_digits=18,
        decimal_places=6,
    )
    error_message: str | None = Field(default=None, min_length=1, max_length=1000)

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def reject_explicit_null_status(self) -> "OptimizationRunUpdate":
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


class OptimizationRunRead(BaseModel):
    id: int
    algorithm_name: str
    status: OptimizationRunStatus
    parameters: dict[str, Any]
    objective_value: Decimal | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
