"""Sentetik fiziksel koli ve başlangıç stoku üretimi."""

from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.config import SyntheticDataProfile
from app.models.catalog import ProductPackaging
from app.models.inventory import Carton, WarehouseLocation


def generate_cartons(
    session: Session,
    profile: SyntheticDataProfile,
    packaging_options: list[ProductPackaging],
    locations: list[WarehouseLocation],
    random: Random,
) -> list[Carton]:
    """Ürün ambalajlarını raflara dağıtarak fiziksel koliler üretir."""
    if not packaging_options:
        raise ValueError("At least one product packaging option is required")
    if not locations:
        raise ValueError("At least one warehouse location is required")

    existing_id = session.scalar(
        select(Carton.id)
        .where(Carton.carton_number.like("SYN-CARTON-%"))
        .limit(1)
    )
    if existing_id is not None:
        raise ValueError("Synthetic cartons already exist")

    shuffled_packaging = packaging_options.copy()
    random.shuffle(shuffled_packaging)
    cartons: list[Carton] = []

    for index in range(1, profile.carton_count + 1):
        packaging = shuffled_packaging[(index - 1) % len(shuffled_packaging)]
        capacity_qty = packaging.units_per_carton
        minimum_qty = max(1, int(capacity_qty * 0.40))
        current_qty = random.randint(minimum_qty, capacity_qty)
        location = random.choice(locations)

        cartons.append(
            Carton(
                carton_number=f"SYN-CARTON-{index:08d}",
                product_packaging_id=packaging.id,
                current_location_id=location.id,
                capacity_qty=capacity_qty,
                current_qty=current_qty,
                reserved_qty=0,
                status="available",
            )
        )

    session.add_all(cartons)
    session.flush()
    return cartons
