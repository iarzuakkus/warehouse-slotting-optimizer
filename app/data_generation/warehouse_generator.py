"""Sentetik depo raf ızgarası üretimi."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.config import SyntheticDataProfile
from app.models.inventory import WarehouseLocation


def generate_warehouse_locations(
    session: Session,
    profile: SyntheticDataProfile,
) -> list[WarehouseLocation]:
    """Profil ölçülerine göre benzersiz raf konumları üretir."""
    existing_id = session.scalar(
        select(WarehouseLocation.id)
        .where(WarehouseLocation.aisle.like("SYN-A%"))
        .limit(1)
    )
    if existing_id is not None:
        raise ValueError("Synthetic warehouse locations already exist")

    locations: list[WarehouseLocation] = []
    for aisle_number in range(1, profile.aisle_count + 1):
        for bay_number in range(1, profile.bays_per_aisle + 1):
            for level_number in range(1, profile.levels_per_bay + 1):
                for slot_number in range(1, profile.slots_per_level + 1):
                    distance = Decimal(
                        aisle_number * 20
                        + bay_number * 3
                        + level_number
                        + slot_number * 0.25
                    ).quantize(Decimal("0.01"))
                    locations.append(
                        WarehouseLocation(
                            aisle=f"SYN-A{aisle_number:03d}",
                            bay=f"B{bay_number:03d}",
                            level=f"L{level_number:02d}",
                            slot=f"S{slot_number:02d}",
                            max_weight_kg=Decimal("1000.000"),
                            distance_from_dispatch_m=distance,
                            is_active=True,
                        )
                    )

    if len(locations) != profile.location_count:
        raise RuntimeError("Generated location count does not match the profile")

    session.add_all(locations)
    session.flush()
    return locations
