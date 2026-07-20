"""Runtime orchestration for deterministic physical carton placement."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.algorithms.carton_placement import (
    CartonDimensions,
    ContainerDimensions,
    PlacedCarton,
    find_placement,
    has_weight_capacity,
)
from app.models.catalog import CartonType, Product
from app.models.inventory import Carton, WarehouseLocation
from app.repositories.warehouse_rack import WarehouseRackRepository


@dataclass(frozen=True)
class CartonPlacementDecision:
    location_id: int
    position_x_cm: Decimal
    position_y_cm: Decimal
    position_z_cm: Decimal
    rotation_degrees: int


class CartonPlacementService:
    def __init__(self, session: Session) -> None:
        self.repository = WarehouseRackRepository(session)

    def find_available_placement(
        self,
        *,
        product: Product,
        carton_type: CartonType,
        current_qty: int,
        preferred_location_id: int | None = None,
        exclude_carton_id: int | None = None,
        excluded_location_ids: set[int] | None = None,
    ) -> CartonPlacementDecision | None:
        racks = self.repository.list_active_racks_for_placement()
        excluded_locations = excluded_location_ids or set()
        locations = sorted(
            (
                location
                for rack in racks
                for location in rack.locations
                if location.is_active and location.id not in excluded_locations
            ),
            key=lambda location: (
                location.aisle,
                location.bay,
                location.level,
                location.slot,
                location.id,
            ),
        )
        if preferred_location_id is not None:
            locations.sort(
                key=lambda location: location.id != preferred_location_id
            )

        incoming_weight_kg = (
            Decimal(current_qty) * product.unit_weight_kg
            if product.unit_weight_kg is not None
            else None
        )
        carton_dimensions = CartonDimensions(
            length_cm=carton_type.outer_length_cm,
            width_cm=carton_type.outer_width_cm,
            height_cm=carton_type.outer_height_cm,
        )
        for location in locations:
            occupied = self._build_occupied_cartons(
                location,
                exclude_carton_id=exclude_carton_id,
            )
            if occupied is None:
                continue
            used_weight_kg = self._used_weight(
                location,
                exclude_carton_id=exclude_carton_id,
            )
            if not has_weight_capacity(
                used_weight_kg,
                incoming_weight_kg,
                location.max_weight_kg,
            ):
                continue
            placement = find_placement(
                ContainerDimensions(
                    width_cm=location.usable_width_cm,
                    depth_cm=location.usable_depth_cm,
                    height_cm=location.usable_height_cm,
                ),
                carton_dimensions,
                occupied,
            )
            if placement is None:
                continue
            return CartonPlacementDecision(
                location_id=location.id,
                position_x_cm=placement.position_x_cm,
                position_y_cm=placement.position_y_cm,
                position_z_cm=placement.position_z_cm,
                rotation_degrees=placement.rotation_degrees,
            )
        return None

    @staticmethod
    def apply_decision(
        carton: Carton,
        decision: CartonPlacementDecision,
    ) -> None:
        carton.current_location_id = decision.location_id
        carton.position_x_cm = decision.position_x_cm
        carton.position_y_cm = decision.position_y_cm
        carton.position_z_cm = decision.position_z_cm
        carton.rotation_degrees = decision.rotation_degrees

    @staticmethod
    def clear_placement(carton: Carton) -> None:
        carton.current_location_id = None
        carton.position_x_cm = None
        carton.position_y_cm = None
        carton.position_z_cm = None
        carton.rotation_degrees = None

    @staticmethod
    def _used_weight(
        location: WarehouseLocation,
        *,
        exclude_carton_id: int | None,
    ) -> Decimal | None:
        used_weight = Decimal("0")
        for carton in location.current_cartons:
            if carton.id == exclude_carton_id:
                continue
            unit_weight = carton.product_packaging.product.unit_weight_kg
            if unit_weight is None:
                return None
            used_weight += Decimal(carton.current_qty) * unit_weight
        return used_weight

    @staticmethod
    def _build_occupied_cartons(
        location: WarehouseLocation,
        *,
        exclude_carton_id: int | None,
    ) -> list[PlacedCarton] | None:
        occupied: list[PlacedCarton] = []
        for carton in location.current_cartons:
            if carton.id == exclude_carton_id:
                continue
            if (
                carton.position_x_cm is None
                or carton.position_y_cm is None
                or carton.position_z_cm is None
                or carton.rotation_degrees is None
            ):
                return None
            carton_type = carton.product_packaging.carton_type
            occupied_width_cm = carton_type.outer_length_cm
            occupied_depth_cm = carton_type.outer_width_cm
            if carton.rotation_degrees == 90:
                occupied_width_cm, occupied_depth_cm = (
                    occupied_depth_cm,
                    occupied_width_cm,
                )
            occupied.append(
                PlacedCarton(
                    carton_id=carton.id,
                    position_x_cm=carton.position_x_cm,
                    position_y_cm=carton.position_y_cm,
                    position_z_cm=carton.position_z_cm,
                    occupied_width_cm=occupied_width_cm,
                    occupied_depth_cm=occupied_depth_cm,
                    occupied_height_cm=carton_type.outer_height_cm,
                    rotation_degrees=carton.rotation_degrees,
                )
            )
        return occupied
