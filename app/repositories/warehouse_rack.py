"""Read-only database queries for logical warehouse racks."""

from sqlalchemy import select
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
