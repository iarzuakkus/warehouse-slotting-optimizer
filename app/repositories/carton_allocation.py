"""Koli ayırma tablosu için SQLAlchemy işlemleri."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.orders import CartonAllocation
from app.schemas.carton_allocation import (
    CartonAllocationCreate,
    CartonAllocationUpdate,
)


class CartonAllocationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, allocation_id: int) -> CartonAllocation | None:
        return self.session.get(CartonAllocation, allocation_id)

    def get_by_line_and_carton(
        self,
        order_line_id: int,
        carton_id: int,
    ) -> CartonAllocation | None:
        statement = select(CartonAllocation).where(
            CartonAllocation.order_line_id == order_line_id,
            CartonAllocation.carton_id == carton_id,
        )
        return self.session.scalar(statement)

    def list_by_order_line(
        self,
        order_line_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CartonAllocation]:
        statement = (
            select(CartonAllocation)
            .where(CartonAllocation.order_line_id == order_line_id)
            .order_by(CartonAllocation.id)
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def total_active_allocated(
        self,
        order_line_id: int,
        exclude_allocation_id: int | None = None,
    ) -> int:
        statement = select(
            func.coalesce(func.sum(CartonAllocation.allocated_qty), 0)
        ).where(
            CartonAllocation.order_line_id == order_line_id,
            CartonAllocation.status != "cancelled",
        )
        if exclude_allocation_id is not None:
            statement = statement.where(
                CartonAllocation.id != exclude_allocation_id
            )
        return int(self.session.scalar(statement) or 0)

    def create(
        self,
        order_line_id: int,
        data: CartonAllocationCreate,
    ) -> CartonAllocation:
        allocation = CartonAllocation(
            order_line_id=order_line_id,
            **data.model_dump(),
        )
        self.session.add(allocation)
        self.session.flush()
        return allocation

    def update(
        self,
        allocation: CartonAllocation,
        data: CartonAllocationUpdate,
    ) -> CartonAllocation:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(allocation, field, value)

        self.session.flush()
        return allocation
