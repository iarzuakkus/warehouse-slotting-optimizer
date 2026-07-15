"""Koli taşıma iş kuralları ve konum güncellemesi."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.inventory import Carton, CartonLocationHistory
from app.repositories.carton import CartonRepository
from app.repositories.carton_location_history import (
    CartonLocationHistoryRepository,
)
from app.repositories.warehouse_location import WarehouseLocationRepository
from app.schemas.carton_location_history import CartonMovementCreate


class CartonMovementNotFoundError(Exception):
    """İstenen koli veya hareket kaydı bulunamadığında kullanılır."""


class CartonMovementLocationNotFoundError(Exception):
    """Hedef raf konumu bulunamadığında kullanılır."""


class CartonMovementConflictError(Exception):
    """Konum veya iş kuralı taşımayı engellediğinde kullanılır."""


class CartonLocationHistoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CartonLocationHistoryRepository(session)
        self.carton_repository = CartonRepository(session)
        self.location_repository = WarehouseLocationRepository(session)

    def _get_carton(self, carton_id: int) -> Carton:
        carton = self.carton_repository.get_by_id(carton_id)
        if carton is None:
            raise CartonMovementNotFoundError(f"Carton {carton_id} not found")
        return carton

    def list_history(
        self,
        carton_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CartonLocationHistory]:
        self._get_carton(carton_id)
        return self.repository.list_by_carton(carton_id, offset, limit)

    def get_history(
        self,
        carton_id: int,
        history_id: int,
    ) -> CartonLocationHistory:
        self._get_carton(carton_id)
        history = self.repository.get_by_id(history_id)
        if history is None or history.carton_id != carton_id:
            raise CartonMovementNotFoundError(
                f"Movement {history_id} not found for carton {carton_id}"
            )
        return history

    def move_carton(
        self,
        carton_id: int,
        data: CartonMovementCreate,
    ) -> CartonLocationHistory:
        carton = self._get_carton(carton_id)
        from_location_id = carton.current_location_id

        if data.to_location_id == from_location_id:
            raise CartonMovementConflictError(
                "Carton is already in the requested location"
            )
        if from_location_id is None and data.to_location_id is None:
            raise CartonMovementConflictError(
                "A carton without a location cannot be removed from a location"
            )

        if data.to_location_id is not None:
            target = self.location_repository.get_by_id(data.to_location_id)
            if target is None:
                raise CartonMovementLocationNotFoundError(
                    f"Warehouse location {data.to_location_id} not found"
                )
            if not target.is_active:
                raise CartonMovementConflictError(
                    f"Warehouse location {data.to_location_id} is inactive"
                )

        try:
            history = self.repository.create(
                carton_id=carton.id,
                from_location_id=from_location_id,
                data=data,
            )
            carton.current_location_id = data.to_location_id
            self.session.flush()
            self.session.commit()
            self.session.refresh(history)
            return history
        except IntegrityError as exc:
            self.session.rollback()
            raise CartonMovementConflictError(
                "Carton movement violates a database rule"
            ) from exc
