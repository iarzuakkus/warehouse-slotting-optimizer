"""Sipariş iş kuralları ve transaction yönetimi."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.orders import Order
from app.repositories.order import OrderRepository
from app.schemas.order import OrderCreate, OrderStatus, OrderUpdate


class OrderNotFoundError(Exception):
    """İstenen sipariş bulunamadığında kullanılır."""


class DuplicateOrderNumberError(Exception):
    """Sipariş numarası tekrarlandığında kullanılır."""


class InvalidOrderStatusTransitionError(Exception):
    """Sipariş durumu geçersiz yönde değiştirilmek istendiğinde kullanılır."""


class InvalidOrderDateError(Exception):
    """Sipariş hedef tarihi sipariş tarihinden önce olduğunda kullanılır."""


class OrderService:
    allowed_status_transitions: dict[OrderStatus, set[OrderStatus]] = {
        "pending": {"allocated", "cancelled"},
        "allocated": {"picking", "cancelled"},
        "picking": {"completed", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = OrderRepository(session)

    def list_orders(
        self,
        offset: int = 0,
        limit: int = 100,
        order_status: OrderStatus | None = None,
    ) -> list[Order]:
        return self.repository.list_orders(
            offset=offset,
            limit=limit,
            order_status=order_status,
        )

    def get_order(self, order_id: int) -> Order:
        order = self.repository.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(f"Order {order_id} not found")
        return order

    def create_order(self, data: OrderCreate) -> Order:
        order_number = data.order_number.upper()
        if self.repository.get_by_order_number(order_number) is not None:
            raise DuplicateOrderNumberError(
                f"Order number {order_number} already exists"
            )
        normalized_data = data.model_copy(update={"order_number": order_number})

        try:
            order = self.repository.create(normalized_data)
            if order.due_at is not None and order.due_at < order.ordered_at:
                raise InvalidOrderDateError(
                    "due_at cannot be earlier than ordered_at"
                )
            self.session.commit()
            self.session.refresh(order)
            return order
        except InvalidOrderDateError:
            self.session.rollback()
            raise
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateOrderNumberError(
                f"Order number {order_number} already exists"
            ) from exc

    def update_order(self, order_id: int, data: OrderUpdate) -> Order:
        order = self.get_order(order_id)

        if data.status is not None and data.status != order.status:
            allowed_statuses = self.allowed_status_transitions[order.status]
            if data.status not in allowed_statuses:
                raise InvalidOrderStatusTransitionError(
                    f"Order status cannot change from {order.status} to {data.status}"
                )

        if (
            "due_at" in data.model_fields_set
            and data.due_at is not None
            and data.due_at < order.ordered_at
        ):
            raise InvalidOrderDateError(
                "due_at cannot be earlier than ordered_at"
            )

        order = self.repository.update(order, data)
        self.session.commit()
        self.session.refresh(order)
        return order
