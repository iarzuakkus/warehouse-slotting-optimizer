"""Talep yoğunluğu ve ürün birlikteliği içeren sipariş üretimi."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.config import SyntheticDataProfile
from app.models.catalog import Product, ProductPackaging
from app.models.orders import Order, OrderLine


@dataclass(frozen=True)
class OrderGenerationResult:
    order_count: int
    order_line_count: int


def build_demand_weights(product_count: int) -> list[float]:
    """Popüler ürünlere daha yüksek olasılık veren Zipf benzeri ağırlıklar."""
    if product_count <= 0:
        raise ValueError("product_count must be positive")
    return [1.0 / (rank**1.10) for rank in range(1, product_count + 1)]


def _select_product_indices(
    product_count: int,
    line_count: int,
    weights: list[float],
    random: Random,
) -> list[int]:
    anchor = random.choices(range(product_count), weights=weights, k=1)[0]
    selected = {anchor}

    # Beşli ürün grupları kontrollü birliktelik örüntüsü oluşturur.
    if line_count > 1 and random.random() < 0.60:
        group_start = (anchor // 5) * 5
        group_indices = list(
            range(group_start, min(group_start + 5, product_count))
        )
        random.shuffle(group_indices)
        selected.update(group_indices[: min(2, line_count - 1)])

    while len(selected) < line_count:
        selected.add(
            random.choices(range(product_count), weights=weights, k=1)[0]
        )
    return list(selected)


def generate_orders(
    session: Session,
    profile: SyntheticDataProfile,
    products: list[Product],
    packaging_options: list[ProductPackaging],
    random: Random,
    reference_time: datetime,
) -> OrderGenerationResult:
    """Tamamlanmış geçmiş siparişler ve bekleyen güncel siparişler üretir."""
    if not products:
        raise ValueError("At least one product is required")
    capacity_by_product_id = {
        packaging.product_id: packaging.units_per_carton
        for packaging in packaging_options
        if packaging.is_default
    }
    if any(product.id not in capacity_by_product_id for product in products):
        raise ValueError("Every product requires a default packaging option")
    if reference_time.tzinfo is None:
        raise ValueError("reference_time must include timezone information")

    existing_id = session.scalar(
        select(Order.id).where(Order.order_number.like("SYN-ORD-%")).limit(1)
    )
    if existing_id is not None:
        raise ValueError("Synthetic orders already exist")

    weights = build_demand_weights(len(products))
    total_lines = 0
    order_specs = (
        ("H", profile.historical_order_count, "completed"),
        ("P", profile.pending_order_count, "pending"),
    )

    for prefix, order_count, order_status in order_specs:
        for batch_start in range(0, order_count, profile.batch_size):
            batch_end = min(batch_start + profile.batch_size, order_count)
            batch_orders: list[Order] = []
            selected_by_order: list[list[int]] = []

            for zero_based_index in range(batch_start, batch_end):
                order_number = zero_based_index + 1
                if order_status == "completed":
                    age = timedelta(
                        seconds=random.randint(0, 365 * 24 * 60 * 60)
                    )
                else:
                    age = timedelta(seconds=random.randint(0, 7 * 24 * 60 * 60))
                ordered_at = reference_time - age
                line_count = random.randint(
                    profile.min_lines_per_order,
                    min(profile.max_lines_per_order, len(products)),
                )
                selected_indices = _select_product_indices(
                    len(products),
                    line_count,
                    weights,
                    random,
                )
                selected_by_order.append(selected_indices)
                batch_orders.append(
                    Order(
                        order_number=f"SYN-ORD-{prefix}-{order_number:09d}",
                        status=order_status,
                        ordered_at=ordered_at,
                        due_at=ordered_at + timedelta(days=random.randint(1, 3)),
                    )
                )

            session.add_all(batch_orders)
            session.flush()

            batch_lines: list[OrderLine] = []
            popular_product_limit = max(1, len(products) // 5)
            for order, selected_indices in zip(
                batch_orders,
                selected_by_order,
                strict=True,
            ):
                for product_index in selected_indices:
                    max_quantity = (
                        12 if product_index < popular_product_limit else 6
                    )
                    max_quantity = min(
                        max_quantity,
                        capacity_by_product_id[products[product_index].id],
                    )
                    ordered_qty = random.randint(1, max_quantity)
                    batch_lines.append(
                        OrderLine(
                            order_id=order.id,
                            product_id=products[product_index].id,
                            ordered_qty=ordered_qty,
                            fulfilled_qty=(
                                ordered_qty if order.status == "completed" else 0
                            ),
                        )
                    )

            session.add_all(batch_lines)
            session.flush()
            total_lines += len(batch_lines)

    return OrderGenerationResult(
        order_count=(
            profile.historical_order_count + profile.pending_order_count
        ),
        order_line_count=total_lines,
    )
