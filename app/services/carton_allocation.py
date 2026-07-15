"""Sipariş satırlarına koli ayırma iş kuralları."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.orders import CartonAllocation, OrderLine
from app.repositories.carton import CartonRepository
from app.repositories.carton_allocation import CartonAllocationRepository
from app.repositories.order import OrderRepository
from app.repositories.order_line import OrderLineRepository
from app.schemas.carton import CartonUpdate
from app.schemas.carton_allocation import (
    CartonAllocationCreate,
    CartonAllocationUpdate,
)


class CartonAllocationNotFoundError(Exception):
    """İstenen koli ayırma kaydı bulunamadığında kullanılır."""


class CartonAllocationReferenceNotFoundError(Exception):
    """Sipariş, satır veya koli bulunamadığında kullanılır."""


class DuplicateCartonAllocationError(Exception):
    """Aynı koli aynı sipariş satırına tekrar ayrıldığında kullanılır."""


class CartonAllocationConflictError(Exception):
    """Stok veya iş akışı kuralı işlemi engellediğinde kullanılır."""


class CartonAllocationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CartonAllocationRepository(session)
        self.carton_repository = CartonRepository(session)
        self.order_repository = OrderRepository(session)
        self.order_line_repository = OrderLineRepository(session)

    def _get_line(self, order_id: int, line_id: int) -> OrderLine:
        order = self.order_repository.get_by_id(order_id)
        if order is None:
            raise CartonAllocationReferenceNotFoundError(
                f"Order {order_id} not found"
            )
        line = self.order_line_repository.get_by_id(line_id)
        if line is None or line.order_id != order_id:
            raise CartonAllocationReferenceNotFoundError(
                f"Order line {line_id} not found in order {order_id}"
            )
        return line

    def _ensure_pending_order(self, order_id: int) -> None:
        order = self.order_repository.get_by_id(order_id)
        if order is None:
            raise CartonAllocationReferenceNotFoundError(
                f"Order {order_id} not found"
            )
        if order.status != "pending":
            raise CartonAllocationConflictError(
                f"Allocations cannot be changed while order status is {order.status}"
            )

    def _get_allocation(
        self,
        line_id: int,
        allocation_id: int,
    ) -> CartonAllocation:
        allocation = self.repository.get_by_id(allocation_id)
        if allocation is None or allocation.order_line_id != line_id:
            raise CartonAllocationNotFoundError(
                f"Allocation {allocation_id} not found in order line {line_id}"
            )
        return allocation

    @staticmethod
    def _carton_status(current_qty: int, reserved_qty: int) -> str:
        if current_qty == 0:
            return "depleted"
        if reserved_qty > 0:
            return "reserved"
        return "available"

    def list_allocations(
        self,
        order_id: int,
        line_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CartonAllocation]:
        self._get_line(order_id, line_id)
        return self.repository.list_by_order_line(line_id, offset, limit)

    def get_allocation(
        self,
        order_id: int,
        line_id: int,
        allocation_id: int,
    ) -> CartonAllocation:
        self._get_line(order_id, line_id)
        return self._get_allocation(line_id, allocation_id)

    def create_allocation(
        self,
        order_id: int,
        line_id: int,
        data: CartonAllocationCreate,
    ) -> CartonAllocation:
        self._ensure_pending_order(order_id)
        line = self._get_line(order_id, line_id)
        carton = self.carton_repository.get_by_id(data.carton_id)
        if carton is None:
            raise CartonAllocationReferenceNotFoundError(
                f"Carton {data.carton_id} not found"
            )
        if carton.status in {"depleted", "quarantined"}:
            raise CartonAllocationConflictError(
                f"Carton {carton.id} cannot be allocated while status is {carton.status}"
            )
        if carton.product_packaging.product_id != line.product_id:
            raise CartonAllocationConflictError(
                "Carton product does not match the order line product"
            )
        if self.repository.get_by_line_and_carton(line_id, carton.id):
            raise DuplicateCartonAllocationError(
                "Carton already exists in this order line"
            )
        if data.allocated_qty > carton.available_qty:
            raise CartonAllocationConflictError(
                "Allocated quantity exceeds carton available quantity"
            )

        unfulfilled_qty = line.ordered_qty - line.fulfilled_qty
        active_total = self.repository.total_active_allocated(line_id)
        if active_total + data.allocated_qty > unfulfilled_qty:
            raise CartonAllocationConflictError(
                "Allocated quantity exceeds the unfulfilled order quantity"
            )

        try:
            allocation = self.repository.create(line_id, data)
            new_reserved_qty = carton.reserved_qty + data.allocated_qty
            self.carton_repository.update(
                carton,
                CartonUpdate(
                    reserved_qty=new_reserved_qty,
                    status=self._carton_status(carton.current_qty, new_reserved_qty),
                ),
            )
            self.session.commit()
            self.session.refresh(allocation)
            return allocation
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateCartonAllocationError(
                "Allocation violates a database rule"
            ) from exc

    def update_allocation(
        self,
        order_id: int,
        line_id: int,
        allocation_id: int,
        data: CartonAllocationUpdate,
    ) -> CartonAllocation:
        self._ensure_pending_order(order_id)
        line = self._get_line(order_id, line_id)
        allocation = self._get_allocation(line_id, allocation_id)
        if allocation.status != "allocated" or allocation.picked_qty > 0:
            raise CartonAllocationConflictError(
                "Only unpicked allocations can be changed"
            )

        carton = self.carton_repository.get_by_id(allocation.carton_id)
        if carton is None:
            raise CartonAllocationReferenceNotFoundError(
                f"Carton {allocation.carton_id} not found"
            )

        if data.status == "cancelled":
            new_reserved_qty = carton.reserved_qty - allocation.allocated_qty
            allocation = self.repository.update(allocation, data)
        else:
            new_allocated_qty = data.allocated_qty or allocation.allocated_qty
            quantity_difference = new_allocated_qty - allocation.allocated_qty
            if quantity_difference > carton.available_qty:
                raise CartonAllocationConflictError(
                    "Allocated quantity exceeds carton available quantity"
                )
            other_total = self.repository.total_active_allocated(
                line_id,
                exclude_allocation_id=allocation.id,
            )
            unfulfilled_qty = line.ordered_qty - line.fulfilled_qty
            if other_total + new_allocated_qty > unfulfilled_qty:
                raise CartonAllocationConflictError(
                    "Allocated quantity exceeds the unfulfilled order quantity"
                )
            new_reserved_qty = carton.reserved_qty + quantity_difference
            allocation = self.repository.update(allocation, data)

        if new_reserved_qty < 0:
            raise CartonAllocationConflictError(
                "Carton reserved quantity cannot become negative"
            )
        self.carton_repository.update(
            carton,
            CartonUpdate(
                reserved_qty=new_reserved_qty,
                status=self._carton_status(carton.current_qty, new_reserved_qty),
            ),
        )
        self.session.commit()
        self.session.refresh(allocation)
        return allocation
