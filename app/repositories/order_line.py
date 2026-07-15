"""Sipariş satırı tablosu için SQLAlchemy işlemleri."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orders import OrderLine
from app.schemas.order_line import OrderLineCreate, OrderLineUpdate


class OrderLineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, order_line_id: int) -> OrderLine | None:
        return self.session.get(OrderLine, order_line_id)

    def get_by_order_and_product(
        self,
        order_id: int,
        product_id: int,
    ) -> OrderLine | None:
        statement = select(OrderLine).where(
            OrderLine.order_id == order_id,
            OrderLine.product_id == product_id,
        )
        return self.session.scalar(statement)

    def list_by_order(
        self,
        order_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[OrderLine]:
        statement = (
            select(OrderLine)
            .where(OrderLine.order_id == order_id)
            .order_by(OrderLine.id)
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def create(self, order_id: int, data: OrderLineCreate) -> OrderLine:
        order_line = OrderLine(order_id=order_id, **data.model_dump())
        self.session.add(order_line)
        self.session.flush()
        return order_line

    def update(self, order_line: OrderLine, data: OrderLineUpdate) -> OrderLine:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(order_line, field, value)

        self.session.flush()
        return order_line

    def delete(self, order_line: OrderLine) -> None:
        self.session.delete(order_line)
        self.session.flush()
