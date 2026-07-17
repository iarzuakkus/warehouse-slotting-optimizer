"""Warehouse rack summary and detail business rules."""

import re
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.inventory import Carton, WarehouseLocation
from app.repositories.warehouse_rack import WarehouseRackRepository
from app.schemas.warehouse_rack import (
    WarehouseRackCartonRead,
    WarehouseRackLocationRead,
    WarehouseRackPackagingRead,
    WarehouseRackProductRead,
    WarehouseRackRead,
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
        locations = self.repository.list_rack_locations(offset=offset, limit=limit)
        locations_by_rack: dict[tuple[str, str], list[WarehouseLocation]] = {}
        for location in locations:
            locations_by_rack.setdefault(
                (location.aisle, location.bay),
                [],
            ).append(location)
        return [
            self._build_summary(rack_locations)
            for rack_locations in locations_by_rack.values()
        ]

    def get_rack(self, aisle: str, bay: str) -> WarehouseRackRead:
        normalized_aisle = aisle.strip().upper()
        normalized_bay = bay.strip().upper()
        locations = self.repository.get_locations(normalized_aisle, normalized_bay)
        if not locations and re.fullmatch(r"A\d+", normalized_aisle):
            synthetic_aisle = f"SYN-{normalized_aisle}"
            locations = self.repository.get_locations(synthetic_aisle, normalized_bay)
            if locations:
                normalized_aisle = synthetic_aisle
        if not locations:
            raise WarehouseRackNotFoundError(
                f"Warehouse rack {normalized_aisle}/{normalized_bay} not found"
            )

        summary = self._build_summary(locations)
        location_details = [self._build_location(location) for location in locations]

        return WarehouseRackRead(
            **summary.model_dump(),
            locations=location_details,
        )

    def _build_summary(
        self,
        locations: list[WarehouseLocation],
    ) -> WarehouseRackSummaryRead:
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
            aisle=locations[0].aisle,
            bay=locations[0].bay,
            level_count=len({location.level for location in locations}),
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
