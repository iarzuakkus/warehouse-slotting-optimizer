"""Geçmiş siparişler için koli ayırma ve toplama hareketi üretimi."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.config import SyntheticDataProfile
from app.models.catalog import ProductPackaging
from app.models.inventory import Carton
from app.models.orders import CartonAllocation, Order, OrderLine, PickOperation


@dataclass(frozen=True)
class FulfillmentGenerationResult:
    allocation_count: int
    pick_operation_count: int


def generate_historical_fulfillment(
    session: Session,
    profile: SyntheticDataProfile,
    cartons: list[Carton],
    packaging_options: list[ProductPackaging],
    random: Random,
) -> FulfillmentGenerationResult:
    """Tamamlanmış sentetik satırlara ayırma ve toplama geçmişi ekler."""
    existing_id = session.scalar(
        select(PickOperation.id)
        .where(PickOperation.operator_reference.like("SYN-OP-%"))
        .limit(1)
    )
    if existing_id is not None:
        raise ValueError("Synthetic fulfillment data already exists")

    product_by_packaging_id = {
        packaging.id: packaging.product_id for packaging in packaging_options
    }
    cartons_by_product_id: dict[int, list[Carton]] = {}
    for carton in cartons:
        product_id = product_by_packaging_id[carton.product_packaging_id]
        cartons_by_product_id.setdefault(product_id, []).append(carton)

    allocation_count = 0
    pick_count = 0
    last_line_id = 0

    while True:
        statement = (
            select(OrderLine, Order.ordered_at)
            .join(Order, Order.id == OrderLine.order_id)
            .where(
                OrderLine.id > last_line_id,
                Order.order_number.like("SYN-ORD-H-%"),
                Order.status == "completed",
            )
            .order_by(OrderLine.id)
            .limit(profile.batch_size)
        )
        rows = list(session.execute(statement))
        if not rows:
            break

        allocations: list[CartonAllocation] = []
        allocation_context: list[tuple[Carton, datetime]] = []
        for line, ordered_at in rows:
            product_cartons = cartons_by_product_id.get(line.product_id)
            if not product_cartons:
                raise RuntimeError(
                    f"No synthetic carton exists for product {line.product_id}"
                )
            carton = random.choice(product_cartons)
            allocations.append(
                CartonAllocation(
                    order_line_id=line.id,
                    carton_id=carton.id,
                    allocated_qty=line.ordered_qty,
                    picked_qty=line.ordered_qty,
                    status="picked",
                )
            )
            allocation_context.append((carton, ordered_at))

        session.add_all(allocations)
        session.flush()

        pick_operations: list[PickOperation] = []
        for allocation, (carton, ordered_at) in zip(
            allocations,
            allocation_context,
            strict=True,
        ):
            pick_operations.append(
                PickOperation(
                    allocation_id=allocation.id,
                    location_id=carton.current_location_id,
                    quantity=allocation.allocated_qty,
                    operator_reference=f"SYN-OP-{random.randint(1, 50):03d}",
                    picked_at=ordered_at
                    + timedelta(minutes=random.randint(5, 24 * 60)),
                )
            )

        session.add_all(pick_operations)
        session.flush()
        allocation_count += len(allocations)
        pick_count += len(pick_operations)
        last_line_id = rows[-1][0].id

    return FulfillmentGenerationResult(
        allocation_count=allocation_count,
        pick_operation_count=pick_count,
    )
