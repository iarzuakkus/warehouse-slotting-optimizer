"""Sipariş satırı iş kuralları ve transaction yönetimi."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.orders import OrderLine
from app.repositories.order import OrderRepository
from app.repositories.order_line import OrderLineRepository
from app.repositories.product import ProductRepository
from app.schemas.order_line import OrderLineCreate, OrderLineUpdate


class OrderLineNotFoundError(Exception):
    """İstenen sipariş satırı bulunamadığında kullanılır."""


class OrderLineReferenceNotFoundError(Exception):
    """Sipariş veya ürün bulunamadığında kullanılır."""


class DuplicateOrderLineError(Exception):
    """Aynı ürün siparişe ikinci kez eklendiğinde kullanılır."""


class OrderLineConflictError(Exception):
    """Sipariş satırı mevcut durumu nedeniyle değiştirilemediğinde kullanılır."""


class OrderLineService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = OrderLineRepository(session)
        self.order_repository = OrderRepository(session)
        self.product_repository = ProductRepository(session)

    def _get_order(self, order_id: int):
        order = self.order_repository.get_by_id(order_id)
        if order is None:
            raise OrderLineReferenceNotFoundError(f"Order {order_id} not found")
        return order

    def _get_line(self, order_id: int, line_id: int) -> OrderLine:
        line = self.repository.get_by_id(line_id)
        if line is None or line.order_id != order_id:
            raise OrderLineNotFoundError(
                f"Order line {line_id} not found in order {order_id}"
            )
        return line

    def _ensure_pending(self, order_id: int) -> None:
        order = self._get_order(order_id)
        if order.status != "pending":
            raise OrderLineConflictError(
                f"Order lines cannot be changed while order status is {order.status}"
            )

    def list_lines(
        self, order_id: int, offset: int = 0, limit: int = 100
    ) -> list[OrderLine]:
        self._get_order(order_id)
        return self.repository.list_by_order(order_id, offset, limit)

    def get_line(self, order_id: int, line_id: int) -> OrderLine:
        self._get_order(order_id)
        return self._get_line(order_id, line_id)

    def create_line(self, order_id: int, data: OrderLineCreate) -> OrderLine:
        self._ensure_pending(order_id)
        product = self.product_repository.get_by_id(data.product_id)
        if product is None:
            raise OrderLineReferenceNotFoundError(f"Product {data.product_id} not found")
        if not product.is_active:
            raise OrderLineConflictError(f"Product {data.product_id} is inactive")
        if self.repository.get_by_order_and_product(order_id, data.product_id):
            raise DuplicateOrderLineError("Product already exists in this order")
        try:
            line = self.repository.create(order_id, data)
            self.session.commit()
            self.session.refresh(line)
            return line
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateOrderLineError(
                "Order line violates a database rule"
            ) from exc

    def update_line(
        self, order_id: int, line_id: int, data: OrderLineUpdate
    ) -> OrderLine:
        self._ensure_pending(order_id)
        line = self._get_line(order_id, line_id)
        if data.ordered_qty is not None and data.ordered_qty < line.fulfilled_qty:
            raise OrderLineConflictError(
                "ordered_qty cannot be lower than fulfilled_qty"
            )
        line = self.repository.update(line, data)
        self.session.commit()
        self.session.refresh(line)
        return line

    def delete_line(self, order_id: int, line_id: int) -> None:
        self._ensure_pending(order_id)
        line = self._get_line(order_id, line_id)
        if line.fulfilled_qty > 0 or line.allocations:
            raise OrderLineConflictError(
                f"Order line {line_id} has fulfillment activity"
            )
        try:
            self.repository.delete(line)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise OrderLineConflictError(
                f"Order line {line_id} is in use"
            ) from exc
