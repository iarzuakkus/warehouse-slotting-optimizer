"""Database operations for physical warehouse racks."""

from decimal import Decimal

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.catalog import ProductPackaging
from app.models.inventory import Carton, WarehouseLocation, WarehouseRack


class WarehouseRackRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_locations(self, aisle: str, bay: str) -> list[WarehouseLocation]:
        statement = (
            select(WarehouseLocation)
            .where(
                WarehouseLocation.aisle == aisle,
                WarehouseLocation.bay == bay,
            )
            .options(
                joinedload(WarehouseLocation.rack),
                selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.product),
                selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.carton_type),
            )
            .execution_options(populate_existing=True)
            .order_by(WarehouseLocation.level, WarehouseLocation.slot)
        )
        return list(self.session.scalars(statement))

    def get_rack(self, aisle: str, bay: str) -> WarehouseRack | None:
        statement = (
            select(WarehouseRack)
            .where(
                WarehouseRack.aisle == aisle,
                WarehouseRack.bay == bay,
            )
            .options(
                selectinload(WarehouseRack.locations)
                .selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.product),
                selectinload(WarehouseRack.locations)
                .selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.carton_type),
            )
            .execution_options(populate_existing=True)
        )
        return self.session.scalar(statement)

    def create_rack(
        self,
        *,
        aisle: str,
        bay: str,
        width_cm: Decimal,
        depth_cm: Decimal,
        level_clear_height_cm: Decimal,
        level_count: int,
        slots_per_level: int,
        frame_thickness_cm: Decimal,
        is_active: bool = True,
    ) -> WarehouseRack:
        rack = WarehouseRack(
            aisle=aisle,
            bay=bay,
            width_cm=width_cm,
            depth_cm=depth_cm,
            level_clear_height_cm=level_clear_height_cm,
            level_count=level_count,
            slots_per_level=slots_per_level,
            frame_thickness_cm=frame_thickness_cm,
            is_active=is_active,
        )
        self.session.add(rack)
        self.session.flush()
        return rack

    def update_grid_size(
        self,
        rack: WarehouseRack,
        *,
        level_count: int,
        slots_per_level: int,
        width_cm: Decimal,
    ) -> WarehouseRack:
        rack.level_count = max(rack.level_count, level_count)
        rack.slots_per_level = max(rack.slots_per_level, slots_per_level)
        rack.width_cm = max(rack.width_cm, width_cm)
        self.session.flush()
        return rack

    def list_racks(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[WarehouseRack]:
        statement = (
            select(WarehouseRack)
            .options(
                selectinload(WarehouseRack.locations)
                .selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.product),
                selectinload(WarehouseRack.locations)
                .selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.carton_type),
            )
            .execution_options(populate_existing=True)
            .order_by(WarehouseRack.aisle, WarehouseRack.bay)
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def list_active_racks_for_placement(self) -> list[WarehouseRack]:
        active_locations = WarehouseRack.locations.and_(
            WarehouseLocation.is_active.is_(True)
        )
        statement = (
            select(WarehouseRack)
            .where(WarehouseRack.is_active.is_(True))
            .options(
                selectinload(active_locations)
                .selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.product),
                selectinload(active_locations)
                .selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.carton_type),
            )
            .execution_options(populate_existing=True)
            .order_by(WarehouseRack.aisle, WarehouseRack.bay)
        )
        return list(self.session.scalars(statement))

    def list_rack_locations(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[WarehouseLocation]:
        rack_keys_statement = (
            select(WarehouseLocation.aisle, WarehouseLocation.bay)
            .group_by(WarehouseLocation.aisle, WarehouseLocation.bay)
            .order_by(WarehouseLocation.aisle, WarehouseLocation.bay)
            .offset(offset)
            .limit(limit)
        )
        rack_keys = [
            (aisle, bay)
            for aisle, bay in self.session.execute(rack_keys_statement)
        ]
        if not rack_keys:
            return []

        statement = (
            select(WarehouseLocation)
            .where(
                tuple_(WarehouseLocation.aisle, WarehouseLocation.bay).in_(rack_keys)
            )
            .options(
                joinedload(WarehouseLocation.rack),
                selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.product),
                selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.carton_type),
            )
            .execution_options(populate_existing=True)
            .order_by(
                WarehouseLocation.aisle,
                WarehouseLocation.bay,
                WarehouseLocation.level,
                WarehouseLocation.slot,
            )
        )
        return list(self.session.scalars(statement))
