"""Optimizasyon çalışmaları ve önerilen koli konumları."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.inventory import Carton, WarehouseLocation


class OptimizationRun(TimestampMixin, Base):
    __tablename__ = "optimization_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="completion_after_start",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="progress_percent_range",
        ),
        Index("ix_optimization_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    seed: Mapped[int | None] = mapped_column(BigInteger)
    algorithm_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), server_default=text("'pending'"), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, server_default=text("'{}'::json"), nullable=False)
    progress_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), server_default=text("0"), nullable=False
    )
    source_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    objective_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(String(1000))

    assignments: Mapped[list["OptimizationAssignment"]] = relationship(
        back_populates="optimization_run", cascade="all, delete-orphan"
    )


class OptimizationAssignment(Base):
    __tablename__ = "optimization_assignments"
    __table_args__ = (
        UniqueConstraint("optimization_run_id", "carton_id"),
        CheckConstraint(
            "from_location_id IS NULL "
            "OR to_location_id IS NULL "
            "OR from_location_id <> to_location_id "
            "OR (from_position_x_cm IS NOT NULL "
            "AND from_position_y_cm IS NOT NULL "
            "AND from_position_z_cm IS NOT NULL "
            "AND from_rotation_degrees IS NOT NULL "
            "AND proposed_position_x_cm IS NOT NULL "
            "AND proposed_position_y_cm IS NOT NULL "
            "AND proposed_position_z_cm IS NOT NULL "
            "AND proposed_rotation_degrees IS NOT NULL "
            "AND (from_position_x_cm <> proposed_position_x_cm "
            "OR from_position_y_cm <> proposed_position_y_cm "
            "OR from_position_z_cm <> proposed_position_z_cm "
            "OR from_rotation_degrees <> proposed_rotation_degrees))",
            name="locations_or_placement_differ",
        ),
        CheckConstraint(
            "proposed_position_x_cm IS NULL OR proposed_position_x_cm >= 0",
            name="proposed_position_x_non_negative",
        ),
        CheckConstraint(
            "proposed_position_y_cm IS NULL OR proposed_position_y_cm >= 0",
            name="proposed_position_y_non_negative",
        ),
        CheckConstraint(
            "proposed_position_z_cm IS NULL OR proposed_position_z_cm >= 0",
            name="proposed_position_z_non_negative",
        ),
        CheckConstraint(
            "proposed_rotation_degrees IS NULL "
            "OR proposed_rotation_degrees IN (0, 90)",
            name="proposed_rotation_valid",
        ),
        CheckConstraint(
            "from_rotation_degrees IS NULL "
            "OR from_rotation_degrees IN (0, 90)",
            name="from_rotation_valid",
        ),
        CheckConstraint(
            "(proposed_position_x_cm IS NULL "
            "AND proposed_position_y_cm IS NULL "
            "AND proposed_position_z_cm IS NULL "
            "AND proposed_rotation_degrees IS NULL) "
            "OR (proposed_position_x_cm IS NOT NULL "
            "AND proposed_position_y_cm IS NOT NULL "
            "AND proposed_position_z_cm IS NOT NULL "
            "AND proposed_rotation_degrees IS NOT NULL)",
            name="proposed_placement_complete",
        ),
        CheckConstraint(
            "(from_position_x_cm IS NULL "
            "AND from_position_y_cm IS NULL "
            "AND from_position_z_cm IS NULL "
            "AND from_rotation_degrees IS NULL) "
            "OR (from_position_x_cm IS NOT NULL "
            "AND from_position_y_cm IS NOT NULL "
            "AND from_position_z_cm IS NOT NULL "
            "AND from_rotation_degrees IS NOT NULL)",
            name="from_placement_complete",
        ),
        CheckConstraint(
            "sequence_number IS NULL OR sequence_number > 0",
            name="sequence_number_positive",
        ),
        CheckConstraint(
            "estimated_duration_seconds IS NULL "
            "OR estimated_duration_seconds >= 0",
            name="estimated_duration_non_negative",
        ),
        CheckConstraint(
            "travel_distance_m IS NULL OR travel_distance_m >= 0",
            name="travel_distance_non_negative",
        ),
        CheckConstraint(
            "result_status IN ('placed', 'unplaced')",
            name="result_status_valid",
        ),
        UniqueConstraint("optimization_run_id", "sequence_number"),
        Index("ix_optimization_assignments_to_location_id", "to_location_id"),
        Index(
            "ix_optimization_assignments_run_sequence",
            "optimization_run_id",
            "sequence_number",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    optimization_run_id: Mapped[int] = mapped_column(
        ForeignKey("optimization_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    carton_id: Mapped[int] = mapped_column(
        ForeignKey("cartons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int | None] = mapped_column()
    result_status: Mapped[str] = mapped_column(
        String(30), server_default=text("'placed'"), nullable=False
    )
    from_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="SET NULL")
    )
    to_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="RESTRICT")
    )
    from_position_x_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    from_position_y_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    from_position_z_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    from_rotation_degrees: Mapped[int | None] = mapped_column()
    proposed_position_x_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    proposed_position_y_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    proposed_position_z_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    proposed_rotation_degrees: Mapped[int | None] = mapped_column()
    assignment_score: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    estimated_duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    travel_distance_m: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    movement_path: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, server_default=text("'[]'::json"), nullable=False
    )
    reasons: Mapped[list[str]] = mapped_column(
        JSON, server_default=text("'[]'::json"), nullable=False
    )
    unplaced_reason: Mapped[str | None] = mapped_column(String(1000))

    optimization_run: Mapped["OptimizationRun"] = relationship(back_populates="assignments")
    carton: Mapped["Carton"] = relationship(back_populates="optimization_assignments")
    from_location: Mapped["WarehouseLocation | None"] = relationship(
        back_populates="assignments_from", foreign_keys=[from_location_id]
    )
    to_location: Mapped["WarehouseLocation | None"] = relationship(
        back_populates="assignments_to", foreign_keys=[to_location_id]
    )
