"""Sentetik depo raf ızgarası üretimi."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_generation.config import SyntheticDataProfile
from app.models.inventory import WarehouseLocation, WarehouseRack


SLOT_USABLE_WIDTH_CM = Decimal("100.00")
USABLE_DEPTH_CM = Decimal("80.00")
LEVEL_CLEAR_HEIGHT_CM = Decimal("60.00")
FRAME_THICKNESS_CM = Decimal("5.00")


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

    existing_rack_id = session.scalar(
        select(WarehouseRack.id)
        .where(WarehouseRack.aisle.like("SYN-A%"))
        .limit(1)
    )
    if existing_rack_id is not None:
        raise ValueError("Synthetic warehouse racks already exist")

    rack_width_cm = (
        SLOT_USABLE_WIDTH_CM * profile.slots_per_level
        + FRAME_THICKNESS_CM * (profile.slots_per_level + 1)
    )
    rack_depth_cm = USABLE_DEPTH_CM + FRAME_THICKNESS_CM * 2
    racks_by_coordinates: dict[tuple[str, str], WarehouseRack] = {}
    for aisle_number in range(1, profile.aisle_count + 1):
        for bay_number in range(1, profile.bays_per_aisle + 1):
            aisle = f"SYN-A{aisle_number:03d}"
            bay = f"B{bay_number:03d}"
            rack = WarehouseRack(
                aisle=aisle,
                bay=bay,
                width_cm=rack_width_cm,
                depth_cm=rack_depth_cm,
                level_clear_height_cm=LEVEL_CLEAR_HEIGHT_CM,
                level_count=profile.levels_per_bay,
                slots_per_level=profile.slots_per_level,
                frame_thickness_cm=FRAME_THICKNESS_CM,
                is_active=True,
            )
            racks_by_coordinates[(aisle, bay)] = rack

    session.add_all(racks_by_coordinates.values())
    session.flush()

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
                            rack_id=racks_by_coordinates[
                                (
                                    f"SYN-A{aisle_number:03d}",
                                    f"B{bay_number:03d}",
                                )
                            ].id,
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
