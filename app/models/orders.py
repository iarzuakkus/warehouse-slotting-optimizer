"""Sipariş, koli ayırma ve toplama hareketleri."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.catalog import Product
    from app.models.inventory import Carton, WarehouseLocation


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'allocated', 'picking', 'completed', 'cancelled')",
            name="status_valid",
        ),
        Index("ix_orders_status_ordered_at", "status", "ordered_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_number: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), server_default=text("'pending'"), nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list["OrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderLine(TimestampMixin, Base):
    __tablename__ = "order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id"),
        CheckConstraint("ordered_qty > 0", name="ordered_qty_positive"),
        CheckConstraint("fulfilled_qty >= 0", name="fulfilled_qty_non_negative"),
        CheckConstraint("fulfilled_qty <= ordered_qty", name="fulfilled_qty_within_ordered"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ordered_qty: Mapped[int] = mapped_column(nullable=False)
    fulfilled_qty: Mapped[int] = mapped_column(server_default=text("0"), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship(back_populates="order_lines")
    allocations: Mapped[list["CartonAllocation"]] = relationship(
        back_populates="order_line", cascade="all, delete-orphan"
    )


class CartonAllocation(TimestampMixin, Base):
    __tablename__ = "carton_allocations"
    __table_args__ = (
        UniqueConstraint("order_line_id", "carton_id"),
        CheckConstraint("allocated_qty > 0", name="allocated_qty_positive"),
        CheckConstraint("picked_qty >= 0", name="picked_qty_non_negative"),
        CheckConstraint("picked_qty <= allocated_qty", name="picked_qty_within_allocated"),
        CheckConstraint(
            "status IN ('allocated', 'picking', 'picked', 'cancelled')",
            name="status_valid",
        ),
        Index("ix_carton_allocations_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_line_id: Mapped[int] = mapped_column(
        ForeignKey("order_lines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    carton_id: Mapped[int] = mapped_column(
        ForeignKey("cartons.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    allocated_qty: Mapped[int] = mapped_column(nullable=False)
    picked_qty: Mapped[int] = mapped_column(server_default=text("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), server_default=text("'allocated'"), nullable=False)

    order_line: Mapped["OrderLine"] = relationship(back_populates="allocations")
    carton: Mapped["Carton"] = relationship(back_populates="allocations")
    pick_operations: Mapped[list["PickOperation"]] = relationship(
        back_populates="allocation", cascade="all, delete-orphan"
    )


class PickOperation(Base):
    __tablename__ = "pick_operations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_pick_operations_allocation_id_picked_at", "allocation_id", "picked_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    allocation_id: Mapped[int] = mapped_column(
        ForeignKey("carton_allocations.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="SET NULL"), index=True
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    operator_reference: Mapped[str | None] = mapped_column(String(100))
    picked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    allocation: Mapped["CartonAllocation"] = relationship(back_populates="pick_operations")
    location: Mapped["WarehouseLocation | None"] = relationship(back_populates="pick_operations")
