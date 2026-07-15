"""Toplama hareketi tablosu için SQLAlchemy işlemleri."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orders import PickOperation
from app.schemas.pick_operation import PickOperationCreate


class PickOperationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, operation_id: int) -> PickOperation | None:
        return self.session.get(PickOperation, operation_id)

    def list_by_allocation(
        self,
        allocation_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[PickOperation]:
        statement = (
            select(PickOperation)
            .where(PickOperation.allocation_id == allocation_id)
            .order_by(PickOperation.picked_at, PickOperation.id)
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def create(
        self,
        allocation_id: int,
        location_id: int | None,
        data: PickOperationCreate,
    ) -> PickOperation:
        operation = PickOperation(
            allocation_id=allocation_id,
            location_id=location_id,
            **data.model_dump(),
        )
        self.session.add(operation)
        self.session.flush()
        return operation
