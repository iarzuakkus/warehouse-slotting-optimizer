"""Sipariş üst bilgisi tablosu için SQLAlchemy işlemleri."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orders import Order
from app.schemas.order import OrderCreate, OrderStatus, OrderUpdate


class OrderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, order_id: int) -> Order | None:
        return self.session.get(Order, order_id)

    def get_by_order_number(self, order_number: str) -> Order | None:
        statement = select(Order).where(Order.order_number == order_number)
        return self.session.scalar(statement)

    def list_orders(
        self,
        offset: int = 0,
        limit: int = 100,
        order_status: OrderStatus | None = None,
    ) -> list[Order]:
        statement = select(Order).order_by(Order.ordered_at.desc(), Order.id.desc())
        if order_status is not None:
            statement = statement.where(Order.status == order_status)
        statement = statement.offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def create(self, data: OrderCreate) -> Order:
        order = Order(**data.model_dump(exclude_none=True))
        self.session.add(order)
        self.session.flush()
        return order

    def update(self, order: Order, data: OrderUpdate) -> Order:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(order, field, value)

        self.session.flush()
        return order
