"""Raf konumları, fiziksel koliler ve konum geçmişi."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.catalog import ProductPackaging
    from app.models.optimization import OptimizationAssignment
    from app.models.orders import CartonAllocation, PickOperation


class WarehouseLocation(TimestampMixin, Base):
    __tablename__ = "warehouse_locations"
    __table_args__ = (
        UniqueConstraint("aisle", "bay", "level", "slot"),
        CheckConstraint("max_weight_kg IS NULL OR max_weight_kg > 0", name="max_weight_positive"),
        CheckConstraint("distance_from_dispatch_m >= 0", name="distance_non_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    aisle: Mapped[str] = mapped_column(String(30), nullable=False)
    bay: Mapped[str] = mapped_column(String(30), nullable=False)
    level: Mapped[str] = mapped_column(String(30), nullable=False)
    slot: Mapped[str] = mapped_column(String(30), nullable=False)
    max_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    distance_from_dispatch_m: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), server_default=text("0"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)

    current_cartons: Mapped[list["Carton"]] = relationship(
        back_populates="current_location", foreign_keys="Carton.current_location_id"
    )
    outbound_movements: Mapped[list["CartonLocationHistory"]] = relationship(
        back_populates="from_location", foreign_keys="CartonLocationHistory.from_location_id"
    )
    inbound_movements: Mapped[list["CartonLocationHistory"]] = relationship(
        back_populates="to_location", foreign_keys="CartonLocationHistory.to_location_id"
    )
    pick_operations: Mapped[list["PickOperation"]] = relationship(back_populates="location")
    assignments_from: Mapped[list["OptimizationAssignment"]] = relationship(
        back_populates="from_location", foreign_keys="OptimizationAssignment.from_location_id"
    )
    assignments_to: Mapped[list["OptimizationAssignment"]] = relationship(
        back_populates="to_location", foreign_keys="OptimizationAssignment.to_location_id"
    )


class Carton(TimestampMixin, Base):
    __tablename__ = "cartons"
    __table_args__ = (
        CheckConstraint("capacity_qty > 0", name="capacity_positive"),
        CheckConstraint("current_qty >= 0", name="current_qty_non_negative"),
        CheckConstraint("current_qty <= capacity_qty", name="current_qty_within_capacity"),
        CheckConstraint("reserved_qty >= 0", name="reserved_qty_non_negative"),
        CheckConstraint("reserved_qty <= current_qty", name="reserved_qty_within_current"),
        CheckConstraint(
            "status IN ('available', 'reserved', 'depleted', 'quarantined')",
            name="status_valid",
        ),
        Index("ix_cartons_status_current_location_id", "status", "current_location_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    carton_number: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    product_packaging_id: Mapped[int] = mapped_column(
        ForeignKey("product_packaging.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    current_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="SET NULL"), index=True
    )
    capacity_qty: Mapped[int] = mapped_column(nullable=False)
    current_qty: Mapped[int] = mapped_column(nullable=False)
    reserved_qty: Mapped[int] = mapped_column(server_default=text("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), server_default=text("'available'"), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Bu değer veritabanında ayrıca saklanmaz.
    @hybrid_property
    def available_qty(self) -> int:
        return self.current_qty - self.reserved_qty

    product_packaging: Mapped["ProductPackaging"] = relationship(back_populates="cartons")
    current_location: Mapped["WarehouseLocation | None"] = relationship(
        back_populates="current_cartons", foreign_keys=[current_location_id]
    )
    allocations: Mapped[list["CartonAllocation"]] = relationship(back_populates="carton")
    location_history: Mapped[list["CartonLocationHistory"]] = relationship(
        back_populates="carton", cascade="all, delete-orphan"
    )
    optimization_assignments: Mapped[list["OptimizationAssignment"]] = relationship(
        back_populates="carton"
    )


class CartonLocationHistory(Base):
    __tablename__ = "carton_location_history"
    __table_args__ = (
        CheckConstraint(
            "from_location_id IS NOT NULL OR to_location_id IS NOT NULL",
            name="at_least_one_location",
        ),
        CheckConstraint(
            "from_location_id IS NULL OR to_location_id IS NULL OR from_location_id <> to_location_id",
            name="locations_differ",
        ),
        Index("ix_carton_location_history_carton_id_moved_at", "carton_id", "moved_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    carton_id: Mapped[int] = mapped_column(ForeignKey("cartons.id", ondelete="CASCADE"), nullable=False)
    from_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="SET NULL")
    )
    to_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(String(255))
    moved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    carton: Mapped["Carton"] = relationship(back_populates="location_history")
    from_location: Mapped["WarehouseLocation | None"] = relationship(
        back_populates="outbound_movements", foreign_keys=[from_location_id]
    )
    to_location: Mapped["WarehouseLocation | None"] = relationship(
        back_populates="inbound_movements", foreign_keys=[to_location_id]
    )
