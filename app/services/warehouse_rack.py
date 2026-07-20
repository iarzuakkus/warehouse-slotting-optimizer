"""Warehouse rack summary and detail business rules."""

import re
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.inventory import Carton, WarehouseLocation, WarehouseRack
from app.repositories.warehouse_rack import WarehouseRackRepository
from app.schemas.warehouse_rack import (
    WarehouseRackCartonRead,
    WarehouseRackLocationRead,
    WarehouseRackPackagingRead,
    WarehouseRackProductRead,
    WarehouseRackRead,
    WarehouseRackSceneCartonRead,
    WarehouseRackSceneLocationRead,
    WarehouseRackSceneRead,
    WarehouseRackSummaryRead,
)


class WarehouseRackNotFoundError(Exception):
    """Raised when an aisle and bay do not contain any locations."""


class WarehouseRackService:
    weight_quantum = Decimal("0.001")
    percent_quantum = Decimal("0.01")

    def __init__(self, session: Session) -> None:
        self.repository = WarehouseRackRepository(session)

    def list_racks(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[WarehouseRackSummaryRead]:
        racks = self.repository.list_racks(offset=offset, limit=limit)
        return [
            self._build_summary(rack)
            for rack in racks
            if rack.locations
        ]

    def list_scene_racks(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[WarehouseRackSceneRead]:
        racks = self.repository.list_racks(offset=offset, limit=limit)
        return [self._build_scene_rack(rack) for rack in racks]

    def get_rack(self, aisle: str, bay: str) -> WarehouseRackRead:
        normalized_aisle = aisle.strip().upper()
        normalized_bay = bay.strip().upper()
        rack = self.repository.get_rack(normalized_aisle, normalized_bay)
        if rack is None and re.fullmatch(r"A\d+", normalized_aisle):
            synthetic_aisle = f"SYN-{normalized_aisle}"
            rack = self.repository.get_rack(synthetic_aisle, normalized_bay)
            if rack is not None:
                normalized_aisle = synthetic_aisle
        if rack is None or not rack.locations:
            raise WarehouseRackNotFoundError(
                f"Warehouse rack {normalized_aisle}/{normalized_bay} not found"
            )

        summary = self._build_summary(rack)
        location_details = [
            self._build_location(location)
            for location in self._sorted_locations(rack)
        ]

        return WarehouseRackRead(
            **summary.model_dump(),
            locations=location_details,
        )

    def _build_summary(
        self,
        rack: WarehouseRack,
    ) -> WarehouseRackSummaryRead:
        locations = rack.locations
        cartons = [
            carton
            for location in locations
            for carton in location.current_cartons
        ]
        total_max_weight = self._sum_optional(
            [location.max_weight_kg for location in locations]
        )
        total_used_weight = self._sum_optional(
            [self._used_weight(location.current_cartons) for location in locations]
        )

        return WarehouseRackSummaryRead(
            aisle=rack.aisle,
            bay=rack.bay,
            level_count=rack.level_count,
            location_count=len(locations),
            active_location_count=sum(location.is_active for location in locations),
            carton_count=len(cartons),
            product_count=len(
                {carton.product_packaging.product_id for carton in cartons}
            ),
            total_max_weight_kg=self._quantize_weight(total_max_weight),
            total_used_weight_kg=self._quantize_weight(total_used_weight),
            weight_utilization_percent=self._utilization_percent(
                total_used_weight,
                total_max_weight,
            ),
        )

    def _build_location(
        self,
        location: WarehouseLocation,
    ) -> WarehouseRackLocationRead:
        used_weight = self._used_weight(location.current_cartons)
        return WarehouseRackLocationRead(
            id=location.id,
            aisle=location.aisle,
            bay=location.bay,
            level=location.level,
            slot=location.slot,
            is_active=location.is_active,
            max_weight_kg=location.max_weight_kg,
            used_weight_kg=self._quantize_weight(used_weight),
            weight_utilization_percent=self._utilization_percent(
                used_weight,
                location.max_weight_kg,
            ),
            distance_from_dispatch_m=location.distance_from_dispatch_m,
            created_at=location.created_at,
            updated_at=location.updated_at,
            cartons=[
                self._build_carton(carton)
                for carton in sorted(
                    location.current_cartons,
                    key=lambda item: (item.carton_number, item.id),
                )
            ],
        )

    def _build_scene_rack(
        self,
        rack: WarehouseRack,
    ) -> WarehouseRackSceneRead:
        locations = self._sorted_locations(rack)
        return WarehouseRackSceneRead(
            aisle=rack.aisle,
            bay=rack.bay,
            width_cm=rack.width_cm,
            depth_cm=rack.depth_cm,
            total_height_cm=rack.total_height_cm,
            level_clear_height_cm=rack.level_clear_height_cm,
            level_count=rack.level_count,
            slots_per_level=rack.slots_per_level,
            location_count=len(locations),
            active_location_count=sum(location.is_active for location in locations),
            locations=[
                self._build_scene_location(location) for location in locations
            ],
        )

    def _build_scene_location(
        self,
        location: WarehouseLocation,
    ) -> WarehouseRackSceneLocationRead:
        used_weight = self._used_weight(location.current_cartons)
        positioned_cartons = [
            carton
            for carton in location.current_cartons
            if self._has_complete_placement(carton)
        ]
        used_volume = sum(
            (
                carton.product_packaging.carton_type.outer_length_cm
                * carton.product_packaging.carton_type.outer_width_cm
                * carton.product_packaging.carton_type.outer_height_cm
                for carton in positioned_cartons
            ),
            start=Decimal("0"),
        )
        usable_volume = (
            location.usable_width_cm
            * location.usable_depth_cm
            * location.usable_height_cm
        )
        return WarehouseRackSceneLocationRead(
            id=location.id,
            level=location.level,
            slot=location.slot,
            is_active=location.is_active,
            usable_width_cm=location.usable_width_cm,
            usable_depth_cm=location.usable_depth_cm,
            usable_height_cm=location.usable_height_cm,
            max_weight_kg=location.max_weight_kg,
            used_weight_kg=self._quantize_weight(used_weight),
            weight_utilization_percent=self._utilization_percent(
                used_weight,
                location.max_weight_kg,
            ),
            volume_utilization_percent=(
                (used_volume / usable_volume) * Decimal("100")
            ).quantize(self.percent_quantum),
            cartons=[
                WarehouseRackSceneCartonRead(
                    id=carton.id,
                    carton_number=carton.carton_number,
                    carton_type_code=carton.product_packaging.carton_type.code,
                    outer_length_cm=(
                        carton.product_packaging.carton_type.outer_length_cm
                    ),
                    outer_width_cm=(
                        carton.product_packaging.carton_type.outer_width_cm
                    ),
                    outer_height_cm=(
                        carton.product_packaging.carton_type.outer_height_cm
                    ),
                    position_x_cm=carton.position_x_cm,
                    position_y_cm=carton.position_y_cm,
                    position_z_cm=carton.position_z_cm,
                    rotation_degrees=carton.rotation_degrees,
                )
                for carton in sorted(
                    positioned_cartons,
                    key=lambda item: (item.carton_number, item.id),
                )
            ],
        )

    @staticmethod
    def _sorted_locations(rack: WarehouseRack) -> list[WarehouseLocation]:
        return sorted(
            rack.locations,
            key=lambda location: (
                location.level,
                location.slot,
                location.id,
            ),
        )

    @staticmethod
    def _has_complete_placement(carton: Carton) -> bool:
        return (
            carton.position_x_cm is not None
            and carton.position_y_cm is not None
            and carton.position_z_cm is not None
            and carton.rotation_degrees is not None
        )

    @staticmethod
    def _build_carton(carton: Carton) -> WarehouseRackCartonRead:
        packaging = carton.product_packaging
        product = packaging.product
        return WarehouseRackCartonRead(
            id=carton.id,
            carton_number=carton.carton_number,
            status=carton.status,
            capacity_qty=carton.capacity_qty,
            current_qty=carton.current_qty,
            reserved_qty=carton.reserved_qty,
            available_qty=carton.available_qty,
            expires_at=carton.expires_at,
            product=WarehouseRackProductRead(
                id=product.id,
                sku=product.sku,
                name=product.name,
                unit_weight_kg=product.unit_weight_kg,
                unit_length_cm=product.unit_length_cm,
                unit_width_cm=product.unit_width_cm,
                unit_height_cm=product.unit_height_cm,
            ),
            packaging=WarehouseRackPackagingRead(
                id=packaging.id,
                units_per_carton=packaging.units_per_carton,
                carton_type_code=packaging.carton_type.code,
            ),
        )

    @staticmethod
    def _used_weight(cartons: list[Carton]) -> Decimal | None:
        weights: list[Decimal] = []
        for carton in cartons:
            unit_weight = carton.product_packaging.product.unit_weight_kg
            if unit_weight is None:
                return None
            weights.append(Decimal(carton.current_qty) * unit_weight)
        return sum(weights, start=Decimal("0"))

    @staticmethod
    def _sum_optional(values: list[Decimal | None]) -> Decimal | None:
        if any(value is None for value in values):
            return None
        return sum((value for value in values if value is not None), Decimal("0"))

    def _quantize_weight(self, value: Decimal | None) -> Decimal | None:
        return value.quantize(self.weight_quantum) if value is not None else None

    def _utilization_percent(
        self,
        used_weight: Decimal | None,
        max_weight: Decimal | None,
    ) -> Decimal | None:
        if used_weight is None or max_weight is None:
            return None
        return ((used_weight / max_weight) * Decimal("100")).quantize(
            self.percent_quantum
        )
