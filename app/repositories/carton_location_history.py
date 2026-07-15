"""Koli konum geçmişi tablosu için SQLAlchemy işlemleri."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import CartonLocationHistory
from app.schemas.carton_location_history import CartonMovementCreate


class CartonLocationHistoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, history_id: int) -> CartonLocationHistory | None:
        return self.session.get(CartonLocationHistory, history_id)

    def list_by_carton(
        self,
        carton_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CartonLocationHistory]:
        statement = (
            select(CartonLocationHistory)
            .where(CartonLocationHistory.carton_id == carton_id)
            .order_by(
                CartonLocationHistory.moved_at,
                CartonLocationHistory.id,
            )
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def create(
        self,
        carton_id: int,
        from_location_id: int | None,
        data: CartonMovementCreate,
    ) -> CartonLocationHistory:
        history = CartonLocationHistory(
            carton_id=carton_id,
            from_location_id=from_location_id,
            **data.model_dump(),
        )
        self.session.add(history)
        self.session.flush()
        return history
