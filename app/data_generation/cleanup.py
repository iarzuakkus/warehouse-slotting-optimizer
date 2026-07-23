"""Yalnizca sentetik depo verisini kontrollu bicimde temizler."""

from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import CartonType, Product, ProductPackaging
from app.models.inventory import Carton, WarehouseLocation, WarehouseRack
from app.models.optimization import OptimizationAssignment, OptimizationRun
from app.models.orders import Order, OrderLine


class SyntheticCleanupSafetyError(Exception):
    """Sentetik kayitlara gercek veriler bagliysa temizlemeyi durdurur."""


@dataclass(frozen=True)
class SyntheticCleanupResult:
    optimization_run_count: int
    order_count: int
    carton_count: int
    location_count: int
    rack_count: int
    product_count: int
    carton_type_count: int


def delete_synthetic_data(session: Session) -> SyntheticCleanupResult:
    """SYN adlandirma sinirlarindaki kayitlari siler; commit etmez."""
    non_synthetic_cartons_in_synthetic_locations = session.scalar(
        select(func.count(Carton.id))
        .join(
            WarehouseLocation,
            WarehouseLocation.id == Carton.current_location_id,
        )
        .where(
            WarehouseLocation.aisle.like("SYN-A%"),
            ~Carton.carton_number.like("SYN-CARTON-%"),
        )
    )
    non_synthetic_cartons_for_synthetic_products = session.scalar(
        select(func.count(Carton.id))
        .join(
            ProductPackaging,
            ProductPackaging.id == Carton.product_packaging_id,
        )
        .join(Product, Product.id == ProductPackaging.product_id)
        .where(
            Product.sku.like("SYN-%"),
            ~Carton.carton_number.like("SYN-CARTON-%"),
        )
    )
    non_synthetic_order_lines_for_synthetic_products = session.scalar(
        select(func.count(OrderLine.id))
        .join(Product, Product.id == OrderLine.product_id)
        .join(Order, Order.id == OrderLine.order_id)
        .where(
            Product.sku.like("SYN-%"),
            ~Order.order_number.like("SYN-ORD-%"),
        )
    )
    non_synthetic_packaging_for_synthetic_carton_types = session.scalar(
        select(func.count(ProductPackaging.id))
        .join(Product, Product.id == ProductPackaging.product_id)
        .join(CartonType, CartonType.id == ProductPackaging.carton_type_id)
        .where(
            CartonType.code.like("SYN-CT-%"),
            ~Product.sku.like("SYN-%"),
        )
    )
    if any(
        (
            non_synthetic_cartons_in_synthetic_locations,
            non_synthetic_cartons_for_synthetic_products,
            non_synthetic_order_lines_for_synthetic_products,
            non_synthetic_packaging_for_synthetic_carton_types,
        )
    ):
        raise SyntheticCleanupSafetyError(
            "Synthetic warehouse data is referenced by non-synthetic records"
        )

    synthetic_location_ids = select(WarehouseLocation.id).where(
        WarehouseLocation.aisle.like("SYN-A%")
    )
    synthetic_carton_ids = select(Carton.id).where(
        Carton.carton_number.like("SYN-CARTON-%")
    )
    affected_optimization_run_ids = select(
        OptimizationAssignment.optimization_run_id
    ).where(
        or_(
            OptimizationAssignment.carton_id.in_(synthetic_carton_ids),
            OptimizationAssignment.from_location_id.in_(synthetic_location_ids),
            OptimizationAssignment.to_location_id.in_(synthetic_location_ids),
        )
    )
    optimization_run_count = _rowcount(
        session.execute(
            delete(OptimizationRun)
            .where(OptimizationRun.id.in_(affected_optimization_run_ids))
            .execution_options(synchronize_session=False)
        )
    )
    order_count = _rowcount(
        session.execute(delete(Order).where(Order.order_number.like("SYN-ORD-%")))
    )
    carton_count = _rowcount(
        session.execute(
            delete(Carton).where(Carton.carton_number.like("SYN-CARTON-%"))
        )
    )
    location_count = _rowcount(
        session.execute(
            delete(WarehouseLocation).where(WarehouseLocation.aisle.like("SYN-A%"))
        )
    )
    rack_count = _rowcount(
        session.execute(
            delete(WarehouseRack).where(WarehouseRack.aisle.like("SYN-A%"))
        )
    )
    product_count = _rowcount(
        session.execute(delete(Product).where(Product.sku.like("SYN-%")))
    )
    carton_type_count = _rowcount(
        session.execute(
            delete(CartonType).where(CartonType.code.like("SYN-CT-%"))
        )
    )
    return SyntheticCleanupResult(
        optimization_run_count=optimization_run_count,
        order_count=order_count,
        carton_count=carton_count,
        location_count=location_count,
        rack_count=rack_count,
        product_count=product_count,
        carton_type_count=carton_type_count,
    )


def _rowcount(result: object) -> int:
    rowcount = getattr(result, "rowcount", 0)
    return max(0, int(rowcount or 0))
