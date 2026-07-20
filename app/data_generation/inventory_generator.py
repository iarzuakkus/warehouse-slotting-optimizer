"""Sentetik fiziksel koli ve başlangıç stoku üretimi."""

from decimal import Decimal
from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.algorithms.carton_placement import (
    CartonDimensions,
    ContainerDimensions,
    PlacedCarton,
    find_placement,
    has_weight_capacity,
)
from app.data_generation.config import SyntheticDataProfile
from app.models.catalog import CartonType, Product, ProductPackaging
from app.models.inventory import Carton, WarehouseLocation, WarehouseRack


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
    packaging_metadata = {
        int(packaging_id): {
            "unit_weight_kg": unit_weight_kg,
            "outer_length_cm": outer_length_cm,
            "outer_width_cm": outer_width_cm,
            "outer_height_cm": outer_height_cm,
        }
        for (
            packaging_id,
            unit_weight_kg,
            outer_length_cm,
            outer_width_cm,
            outer_height_cm,
        ) in session.execute(
            select(
                ProductPackaging.id,
                Product.unit_weight_kg,
                CartonType.outer_length_cm,
                CartonType.outer_width_cm,
                CartonType.outer_height_cm,
            )
            .join(Product, Product.id == ProductPackaging.product_id)
            .join(CartonType, CartonType.id == ProductPackaging.carton_type_id)
            .where(
                ProductPackaging.id.in_(
                    [packaging.id for packaging in packaging_options]
                )
            )
        )
    }
    location_metadata = {
        int(location_id): {
            "max_weight_kg": max_weight_kg,
            "container": ContainerDimensions(
                width_cm=(
                    rack_width_cm
                    - frame_thickness_cm * (slots_per_level + 1)
                )
                / slots_per_level,
                depth_cm=rack_depth_cm - frame_thickness_cm * 2,
                height_cm=level_clear_height_cm,
            ),
        }
        for (
            location_id,
            max_weight_kg,
            rack_width_cm,
            rack_depth_cm,
            level_clear_height_cm,
            slots_per_level,
            frame_thickness_cm,
        ) in session.execute(
            select(
                WarehouseLocation.id,
                WarehouseLocation.max_weight_kg,
                WarehouseRack.width_cm,
                WarehouseRack.depth_cm,
                WarehouseRack.level_clear_height_cm,
                WarehouseRack.slots_per_level,
                WarehouseRack.frame_thickness_cm,
            )
            .join(WarehouseRack, WarehouseRack.id == WarehouseLocation.rack_id)
            .where(
                WarehouseLocation.id.in_([location.id for location in locations]),
                WarehouseLocation.is_active.is_(True),
                WarehouseRack.is_active.is_(True),
            )
        )
    }
    ordered_location_ids = [
        location.id for location in locations if location.id in location_metadata
    ]
    if not ordered_location_ids:
        raise ValueError("At least one active physical warehouse location is required")

    placements_by_location: dict[int, list[PlacedCarton]] = {
        location_id: [] for location_id in ordered_location_ids
    }
    used_weight_by_location = {
        location_id: Decimal("0") for location_id in ordered_location_ids
    }
    cartons: list[Carton] = []

    for index in range(1, profile.carton_count + 1):
        packaging = shuffled_packaging[(index - 1) % len(shuffled_packaging)]
        metadata = packaging_metadata[packaging.id]
        capacity_qty = packaging.units_per_carton
        minimum_qty = max(1, int(capacity_qty * 0.40))
        current_qty = random.randint(minimum_qty, capacity_qty)
        unit_weight_kg = metadata["unit_weight_kg"]
        incoming_weight_kg = (
            Decimal(current_qty) * unit_weight_kg
            if unit_weight_kg is not None
            else None
        )
        dimensions = CartonDimensions(
            length_cm=metadata["outer_length_cm"],
            width_cm=metadata["outer_width_cm"],
            height_cm=metadata["outer_height_cm"],
        )
        round_robin_start = (index - 1) % len(ordered_location_ids)
        candidate_location_ids = (
            ordered_location_ids[round_robin_start:]
            + ordered_location_ids[:round_robin_start]
        )

        selected_location_id: int | None = None
        selected_placement = None
        for location_id in candidate_location_ids:
            location_data = location_metadata[location_id]
            if not has_weight_capacity(
                used_weight_by_location[location_id],
                incoming_weight_kg,
                location_data["max_weight_kg"],
            ):
                continue
            placement = find_placement(
                location_data["container"],
                dimensions,
                placements_by_location[location_id],
            )
            if placement is None:
                continue
            selected_location_id = location_id
            selected_placement = placement
            placements_by_location[location_id].append(
                placement.to_placed_carton(carton_id=index)
            )
            used_weight_by_location[location_id] += incoming_weight_kg
            break

        cartons.append(
            Carton(
                carton_number=f"SYN-CARTON-{index:08d}",
                product_packaging_id=packaging.id,
                current_location_id=selected_location_id,
                position_x_cm=(
                    selected_placement.position_x_cm
                    if selected_placement is not None
                    else None
                ),
                position_y_cm=(
                    selected_placement.position_y_cm
                    if selected_placement is not None
                    else None
                ),
                position_z_cm=(
                    selected_placement.position_z_cm
                    if selected_placement is not None
                    else None
                ),
                rotation_degrees=(
                    selected_placement.rotation_degrees
                    if selected_placement is not None
                    else None
                ),
                capacity_qty=capacity_qty,
                current_qty=current_qty,
                reserved_qty=0,
                status="available",
            )
        )

    session.add_all(cartons)
    session.flush()
    return cartons
