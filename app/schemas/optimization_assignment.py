"""Optimizasyon yerleşim önerisi API şemaları."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OptimizationAssignmentCreate(BaseModel):
    carton_id: int = Field(gt=0)
    to_location_id: int = Field(gt=0)
    assignment_score: Decimal | None = Field(
        default=None,
        max_digits=18,
        decimal_places=6,
    )


class OptimizationAssignmentRead(BaseModel):
    id: int
    optimization_run_id: int
    carton_id: int
    from_location_id: int | None
    to_location_id: int
    proposed_position_x_cm: Decimal | None
    proposed_position_y_cm: Decimal | None
    proposed_position_z_cm: Decimal | None
    proposed_rotation_degrees: int | None
    assignment_score: Decimal | None

    model_config = ConfigDict(from_attributes=True)
