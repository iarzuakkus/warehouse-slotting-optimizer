"""Toplama hareketi iş kuralları ve stok güncellemeleri."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.orders import CartonAllocation, PickOperation
from app.repositories.carton import CartonRepository
from app.repositories.carton_allocation import CartonAllocationRepository
from app.repositories.order import OrderRepository
from app.repositories.order_line import OrderLineRepository
from app.repositories.pick_operation import PickOperationRepository
from app.schemas.pick_operation import PickOperationCreate


class PickOperationNotFoundError(Exception):
    """İstenen toplama hareketi bulunamadığında kullanılır."""


class PickOperationReferenceNotFoundError(Exception):
    """Sipariş, satır, ayırma veya koli bulunamadığında kullanılır."""


class PickOperationConflictError(Exception):
    """Stok veya iş akışı kuralı toplamayı engellediğinde kullanılır."""


class PickOperationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PickOperationRepository(session)
        self.order_repository = OrderRepository(session)
        self.order_line_repository = OrderLineRepository(session)
        self.allocation_repository = CartonAllocationRepository(session)
        self.carton_repository = CartonRepository(session)

    def _get_context(
        self,
        order_id: int,
        line_id: int,
        allocation_id: int,
    ) -> tuple:
        order = self.order_repository.get_by_id(order_id)
        if order is None:
            raise PickOperationReferenceNotFoundError(
                f"Order {order_id} not found"
            )

        line = self.order_line_repository.get_by_id(line_id)
        if line is None or line.order_id != order_id:
            raise PickOperationReferenceNotFoundError(
                f"Order line {line_id} not found in order {order_id}"
            )

        allocation = self.allocation_repository.get_by_id(allocation_id)
        if allocation is None or allocation.order_line_id != line_id:
            raise PickOperationReferenceNotFoundError(
                f"Allocation {allocation_id} not found in order line {line_id}"
            )
        return order, line, allocation

    def _get_operation(
        self,
        allocation: CartonAllocation,
        operation_id: int,
    ) -> PickOperation:
        operation = self.repository.get_by_id(operation_id)
        if operation is None or operation.allocation_id != allocation.id:
            raise PickOperationNotFoundError(
                f"Pick operation {operation_id} not found in allocation {allocation.id}"
            )
        return operation

    @staticmethod
    def _carton_status(current_qty: int, reserved_qty: int) -> str:
        if current_qty == 0:
            return "depleted"
        if reserved_qty > 0:
            return "reserved"
        return "available"

    def list_operations(
        self,
        order_id: int,
        line_id: int,
        allocation_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[PickOperation]:
        self._get_context(order_id, line_id, allocation_id)
        return self.repository.list_by_allocation(allocation_id, offset, limit)

    def get_operation(
        self,
        order_id: int,
        line_id: int,
        allocation_id: int,
        operation_id: int,
    ) -> PickOperation:
        _, _, allocation = self._get_context(order_id, line_id, allocation_id)
        return self._get_operation(allocation, operation_id)

    def create_operation(
        self,
        order_id: int,
        line_id: int,
        allocation_id: int,
        data: PickOperationCreate,
    ) -> PickOperation:
        order, line, allocation = self._get_context(
            order_id,
            line_id,
            allocation_id,
        )
        if order.status not in {"allocated", "picking"}:
            raise PickOperationConflictError(
                f"Picking cannot start while order status is {order.status}"
            )
        if allocation.status not in {"allocated", "picking"}:
            raise PickOperationConflictError(
                f"Allocation cannot be picked while status is {allocation.status}"
            )

        remaining_qty = allocation.allocated_qty - allocation.picked_qty
        if data.quantity > remaining_qty:
            raise PickOperationConflictError(
                "Pick quantity exceeds the remaining allocated quantity"
            )

        carton = self.carton_repository.get_by_id(allocation.carton_id)
        if carton is None:
            raise PickOperationReferenceNotFoundError(
                f"Carton {allocation.carton_id} not found"
            )
        if carton.status == "quarantined":
            raise PickOperationConflictError("A quarantined carton cannot be picked")
        if data.quantity > carton.current_qty or data.quantity > carton.reserved_qty:
            raise PickOperationConflictError(
                "Pick quantity exceeds carton stock or reserved quantity"
            )

        try:
            operation = self.repository.create(
                allocation_id=allocation.id,
                location_id=carton.current_location_id,
                data=data,
            )

            allocation.picked_qty += data.quantity
            allocation.status = (
                "picked"
                if allocation.picked_qty == allocation.allocated_qty
                else "picking"
            )

            carton.current_qty -= data.quantity
            carton.reserved_qty -= data.quantity
            carton.status = self._carton_status(
                carton.current_qty,
                carton.reserved_qty,
            )

            line.fulfilled_qty += data.quantity
            order.status = (
                "completed"
                if all(item.fulfilled_qty == item.ordered_qty for item in order.lines)
                else "picking"
            )

            self.session.flush()
            self.session.commit()
            self.session.refresh(operation)
            return operation
        except IntegrityError as exc:
            self.session.rollback()
            raise PickOperationConflictError(
                "Pick operation violates a database rule"
            ) from exc
