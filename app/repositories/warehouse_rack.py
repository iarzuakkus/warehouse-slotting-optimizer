"""Read-only database queries for logical warehouse racks."""

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.catalog import ProductPackaging
from app.models.inventory import Carton, WarehouseLocation


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
                selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.product),
                selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.carton_type),
            )
            .order_by(WarehouseLocation.level, WarehouseLocation.slot)
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
                selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.product),
                selectinload(WarehouseLocation.current_cartons)
                .selectinload(Carton.product_packaging)
                .joinedload(ProductPackaging.carton_type),
            )
            .order_by(
                WarehouseLocation.aisle,
                WarehouseLocation.bay,
                WarehouseLocation.level,
                WarehouseLocation.slot,
            )
        )
        return list(self.session.scalars(statement))
