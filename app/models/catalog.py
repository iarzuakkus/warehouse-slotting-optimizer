"""Ürün, koli tipi ve ürün ambalaj tanımları."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.inventory import Carton
    from app.models.orders import OrderLine


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("unit_weight_kg IS NULL OR unit_weight_kg > 0", name="unit_weight_positive"),
        CheckConstraint(
            "unit_length_cm IS NULL OR unit_length_cm > 0",
            name="unit_length_positive",
        ),
        CheckConstraint(
            "unit_width_cm IS NULL OR unit_width_cm > 0",
            name="unit_width_positive",
        ),
        CheckConstraint(
            "unit_height_cm IS NULL OR unit_height_cm > 0",
            name="unit_height_positive",
        ),
        CheckConstraint(
            "(unit_length_cm IS NULL AND unit_width_cm IS NULL AND unit_height_cm IS NULL) "
            "OR (unit_length_cm IS NOT NULL AND unit_width_cm IS NOT NULL "
            "AND unit_height_cm IS NOT NULL)",
            name="unit_dimensions_complete",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_length_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    unit_width_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    unit_height_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)

    packaging_options: Mapped[list["ProductPackaging"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    order_lines: Mapped[list["OrderLine"]] = relationship(back_populates="product")


class CartonType(TimestampMixin, Base):
    __tablename__ = "carton_types"
    __table_args__ = (
        CheckConstraint("inner_length_cm > 0", name="inner_length_positive"),
        CheckConstraint("inner_width_cm > 0", name="inner_width_positive"),
        CheckConstraint("inner_height_cm > 0", name="inner_height_positive"),
        CheckConstraint("outer_length_cm > 0", name="outer_length_positive"),
        CheckConstraint("outer_width_cm > 0", name="outer_width_positive"),
        CheckConstraint("outer_height_cm > 0", name="outer_height_positive"),
        CheckConstraint(
            "outer_length_cm >= inner_length_cm",
            name="outer_length_not_smaller_than_inner",
        ),
        CheckConstraint(
            "outer_width_cm >= inner_width_cm",
            name="outer_width_not_smaller_than_inner",
        ),
        CheckConstraint(
            "outer_height_cm >= inner_height_cm",
            name="outer_height_not_smaller_than_inner",
        ),
        CheckConstraint("max_weight_kg > 0", name="max_weight_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    inner_length_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    inner_width_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    inner_height_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    outer_length_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    outer_width_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    outer_height_cm: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    max_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)

    packaging_options: Mapped[list["ProductPackaging"]] = relationship(back_populates="carton_type")


class ProductPackaging(TimestampMixin, Base):
    __tablename__ = "product_packaging"
    __table_args__ = (
        UniqueConstraint("product_id", "carton_type_id"),
        CheckConstraint("units_per_carton > 0", name="units_per_carton_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    carton_type_id: Mapped[int] = mapped_column(
        ForeignKey("carton_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    units_per_carton: Mapped[int] = mapped_column(nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)

    product: Mapped["Product"] = relationship(back_populates="packaging_options")
    carton_type: Mapped["CartonType"] = relationship(back_populates="packaging_options")
    cartons: Mapped[list["Carton"]] = relationship(back_populates="product_packaging")
