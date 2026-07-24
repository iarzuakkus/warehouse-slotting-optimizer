"""Simulation scenario API request and response schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SimulationScenarioStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
]
SimulationAssignmentStatus = Literal["placed", "unplaced"]
SimulationEquipmentType = Literal["cart", "pallet_jack", "forklift"]
SimulationMoveBatchStopType = Literal["pickup", "dropoff"]
SimulationBatchAnimationEventType = Literal[
    "travel",
    "pickup",
    "dropoff",
    "staging_pickup",
    "staging_dropoff",
]


class SimulationObjectiveWeights(BaseModel):
    """Weights for soft objectives; hard physical rules are not weighted."""

    same_sku_location: Decimal = Field(default=Decimal("8"), ge=0)
    same_rack: Decimal = Field(default=Decimal("4"), ge=0)
    nearby_aisle: Decimal = Field(default=Decimal("2"), ge=0)
    lower_level_for_heavy: Decimal = Field(default=Decimal("5"), ge=0)
    dispatch_distance: Decimal = Field(default=Decimal("7"), ge=0)
    co_shipment_proximity: Decimal = Field(default=Decimal("3"), ge=0)
    location_consolidation: Decimal = Field(default=Decimal("4"), ge=0)
    split_sku: Decimal = Field(default=Decimal("6"), ge=0)
    moves: Decimal = Field(default=Decimal("5"), ge=0)
    volume_utilization: Decimal = Field(default=Decimal("4"), ge=0)

    @model_validator(mode="after")
    def require_an_active_objective(self) -> "SimulationObjectiveWeights":
        if not any(value > 0 for value in self.__dict__.values()):
            raise ValueError("at least one objective weight must be greater than zero")
        return self


class SimulationScenarioParameters(BaseModel):
    """Configurable scenario behavior stored in OptimizationRun.parameters."""

    group_same_sku: bool = True
    prefer_lower_levels_for_heavy_cartons: bool = True
    minimize_dispatch_distance: bool = True
    minimize_moves: bool = True
    improve_volume_utilization: bool = True
    equipment_type: SimulationEquipmentType = "cart"
    max_batch_weight_kg: Decimal = Field(
        default=Decimal("250"),
        gt=0,
        max_digits=12,
        decimal_places=3,
    )
    max_batch_volume_m3: Decimal = Field(
        default=Decimal("1.2"),
        gt=0,
        max_digits=12,
        decimal_places=6,
    )
    max_cartons_per_batch: int = Field(default=12, ge=1)
    objective_weights: SimulationObjectiveWeights = Field(
        default_factory=SimulationObjectiveWeights
    )
    aisle_filter: list[str] | None = Field(default=None, min_length=1)
    level_filter: list[str] | None = Field(default=None, min_length=1)

    model_config = ConfigDict(str_strip_whitespace=True)


class SimulationScenarioCreate(SimulationScenarioParameters):
    name: str = Field(min_length=1, max_length=200)
    seed: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    algorithm_name: str = Field(
        default="deterministic_slotting_v1",
        min_length=1,
        max_length=100,
    )


class SimulationScenarioUpdate(BaseModel):
    """Editable draft fields; completed scenarios remain immutable in service."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    seed: int | None = Field(
        default=None,
        ge=0,
        le=9_223_372_036_854_775_807,
    )
    algorithm_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    group_same_sku: bool | None = None
    prefer_lower_levels_for_heavy_cartons: bool | None = None
    minimize_dispatch_distance: bool | None = None
    minimize_moves: bool | None = None
    improve_volume_utilization: bool | None = None
    equipment_type: SimulationEquipmentType | None = None
    max_batch_weight_kg: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=3,
    )
    max_batch_volume_m3: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=6,
    )
    max_cartons_per_batch: int | None = Field(default=None, ge=1)
    objective_weights: SimulationObjectiveWeights | None = None
    aisle_filter: list[str] | None = Field(default=None, min_length=1)
    level_filter: list[str] | None = Field(default=None, min_length=1)

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def reject_explicit_null_values(self) -> "SimulationScenarioUpdate":
        null_fields = [
            field_name
            for field_name in self.model_fields_set
            if getattr(self, field_name) is None
        ]
        if null_fields:
            joined_fields = ", ".join(sorted(null_fields))
            raise ValueError(f"scenario update fields cannot be null: {joined_fields}")
        return self


class SimulationMetricSet(BaseModel):
    total_dispatch_distance: Decimal = Field(ge=0)
    average_dispatch_distance: Decimal = Field(ge=0)
    weight_utilization_percent: Decimal | None = Field(default=None, ge=0)
    volume_utilization_percent: Decimal = Field(ge=0)
    used_location_count: int = Field(ge=0)
    split_sku_count: int = Field(ge=0)
    moved_carton_count: int = Field(ge=0)
    unplaced_carton_count: int = Field(ge=0)
    objective_score: Decimal


class SimulationScenarioResultRead(BaseModel):
    current: SimulationMetricSet
    proposed: SimulationMetricSet
    objective_improvement_percent: Decimal | None
    estimated_duration_seconds: Decimal = Field(ge=0)
    total_movement_distance_m: Decimal = Field(ge=0)


class SimulationScenarioRead(BaseModel):
    id: int
    name: str
    seed: int
    algorithm_name: str
    status: SimulationScenarioStatus
    progress_percent: Decimal = Field(ge=0, le=100)
    parameters: SimulationScenarioParameters
    result: SimulationScenarioResultRead | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class SimulationPathPointRead(BaseModel):
    sequence: int = Field(ge=0)
    node_id: str = Field(min_length=1)
    x: Decimal
    y: Decimal


class SimulationMoveRead(BaseModel):
    id: int
    sequence: int = Field(gt=0)
    result_status: SimulationAssignmentStatus
    carton_id: int
    carton_number: str
    product_id: int
    sku: str
    from_location_id: int | None
    to_location_id: int | None
    from_position_x_cm: Decimal | None
    from_position_y_cm: Decimal | None
    from_position_z_cm: Decimal | None
    from_rotation_degrees: int | None
    proposed_position_x_cm: Decimal | None
    proposed_position_y_cm: Decimal | None
    proposed_position_z_cm: Decimal | None
    proposed_rotation_degrees: int | None
    assignment_score: Decimal | None
    estimated_duration_seconds: Decimal | None = Field(default=None, ge=0)
    travel_distance_m: Decimal | None = Field(default=None, ge=0)
    path: list[SimulationPathPointRead]
    reasons: list[str]
    unplaced_reason: str | None


class SimulationMoveListRead(BaseModel):
    scenario_id: int
    move_count: int = Field(ge=0)
    unplaced_count: int = Field(ge=0)
    moves: list[SimulationMoveRead]


class SimulationMoveBatchStopRead(BaseModel):
    sequence: int = Field(gt=0)
    type: SimulationMoveBatchStopType
    location_id: int = Field(gt=0)
    carton_ids: list[int] = Field(min_length=1)


class SimulationMoveBatchItemRead(BaseModel):
    move_sequence: int = Field(gt=0)
    carton_id: int = Field(gt=0)
    carton_number: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    weight_kg: Decimal = Field(ge=0)
    volume_m3: Decimal = Field(gt=0)
    from_location_id: int | None = Field(default=None, gt=0)
    to_location_id: int = Field(gt=0)


class SimulationMoveBatchValidationRead(BaseModel):
    move_sequence: int = Field(gt=0)
    carton_id: int = Field(gt=0)
    code: Literal[
        "max_batch_weight_exceeded",
        "max_batch_volume_exceeded",
    ]
    message: str = Field(min_length=1)


class SimulationMoveBatchRead(BaseModel):
    sequence: int = Field(gt=0)
    equipment_type: SimulationEquipmentType
    carton_count: int = Field(ge=1)
    total_weight_kg: Decimal = Field(ge=0)
    total_volume_m3: Decimal = Field(gt=0)
    estimated_distance_m: Decimal = Field(ge=0)
    estimated_duration_seconds: Decimal = Field(ge=0)
    capacity_utilization_percent: Decimal = Field(ge=0, le=100)
    move_sequences: list[int]
    staged_move_sequences: list[int] = Field(default_factory=list)
    finalized_move_sequences: list[int] = Field(default_factory=list)
    items: list[SimulationMoveBatchItemRead] = Field(min_length=1)
    stops: list[SimulationMoveBatchStopRead] = Field(min_length=1)
    reasons: list[str]
    requires_staging_buffer: bool = False


class SimulationMoveBatchListRead(BaseModel):
    scenario_id: int = Field(gt=0)
    equipment_type: SimulationEquipmentType
    batch_count: int = Field(ge=0)
    carton_move_count: int = Field(ge=0)
    operational_distance_m: Decimal = Field(ge=0)
    individual_distance_m: Decimal = Field(ge=0)
    estimated_duration_seconds: Decimal = Field(ge=0)
    capacity_utilization_percent: Decimal = Field(ge=0, le=100)
    requires_staging_buffer: bool = False
    staging_move_sequences: list[int] = Field(default_factory=list)
    batches: list[SimulationMoveBatchRead]
    unbatched_items: list[SimulationMoveBatchItemRead] = Field(
        default_factory=list
    )
    validation_errors: list[SimulationMoveBatchValidationRead] = Field(
        default_factory=list
    )


class SimulationBatchAnimationWaypointRead(BaseModel):
    """A timestamped warehouse-graph point followed by the equipment."""

    sequence: int = Field(gt=0)
    node_id: str = Field(min_length=1)
    x_m: Decimal
    y_m: Decimal
    z_m: Decimal = Field(default=Decimal("0"), ge=0)
    cumulative_distance_m: Decimal = Field(ge=0)
    elapsed_seconds: Decimal = Field(ge=0)


class SimulationBatchAnimationEventRead(BaseModel):
    """One deterministic travel or carton-handling animation event."""

    sequence: int = Field(gt=0)
    type: SimulationBatchAnimationEventType
    start_seconds: Decimal = Field(ge=0)
    end_seconds: Decimal = Field(ge=0)
    location_id: int | None = Field(default=None, gt=0)
    carton_ids: list[int] = Field(default_factory=list)
    waypoints: list[SimulationBatchAnimationWaypointRead] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_event_time_range(
        self,
    ) -> "SimulationBatchAnimationEventRead":
        if self.end_seconds < self.start_seconds:
            raise ValueError(
                "animation event end_seconds cannot precede start_seconds"
            )
        return self


class SimulationBatchAnimationRead(BaseModel):
    """Frontend-ready timeline for one material-handling batch."""

    scenario_id: int = Field(gt=0)
    batch_sequence: int = Field(gt=0)
    equipment_type: SimulationEquipmentType
    source_scene_step: int = Field(ge=0)
    target_scene_step: int = Field(gt=0)
    route_distance_m: Decimal = Field(ge=0)
    estimated_duration_seconds: Decimal = Field(ge=0)
    events: list[SimulationBatchAnimationEventRead] = Field(min_length=1)
