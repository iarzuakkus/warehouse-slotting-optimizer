"""Sentetik veri üretim adımlarının transaction yöneticisi."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from random import Random

from sqlalchemy.orm import Session

from app.data_generation.catalog_generator import generate_catalog
from app.data_generation.config import get_profile
from app.data_generation.fulfillment_generator import (
    generate_historical_fulfillment,
)
from app.data_generation.inventory_generator import generate_cartons
from app.data_generation.order_generator import generate_orders
from app.data_generation.warehouse_generator import generate_warehouse_locations


@dataclass(frozen=True)
class SyntheticGenerationSummary:
    profile: str
    seed: int
    product_count: int
    carton_type_count: int
    packaging_count: int
    location_count: int
    carton_count: int
    order_count: int
    order_line_count: int
    allocation_count: int
    pick_operation_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


def generate_synthetic_data(
    session: Session,
    profile_name: str = "small",
    seed: int = 42,
    reference_time: datetime | None = None,
) -> SyntheticGenerationSummary:
    """Tüm sentetik veriyi bağımlılık sırasıyla ve atomik olarak üretir."""
    profile = get_profile(profile_name)
    random = Random(seed)
    effective_reference_time = reference_time or datetime.now(timezone.utc)

    try:
        catalog = generate_catalog(session, profile, random)
        locations = generate_warehouse_locations(session, profile)
        cartons = generate_cartons(
            session,
            profile,
            catalog.packaging_options,
            locations,
            random,
        )
        orders = generate_orders(
            session,
            profile,
            catalog.products,
            catalog.packaging_options,
            random,
            effective_reference_time,
        )
        fulfillment = generate_historical_fulfillment(
            session,
            profile,
            cartons,
            catalog.packaging_options,
            random,
        )

        summary = SyntheticGenerationSummary(
            profile=profile.name,
            seed=seed,
            product_count=len(catalog.products),
            carton_type_count=len(catalog.carton_types),
            packaging_count=len(catalog.packaging_options),
            location_count=len(locations),
            carton_count=len(cartons),
            order_count=orders.order_count,
            order_line_count=orders.order_line_count,
            allocation_count=fulfillment.allocation_count,
            pick_operation_count=fulfillment.pick_operation_count,
        )
        session.commit()
        return summary
    except Exception:
        session.rollback()
        raise
