"""Fiziksel koli tablosu için SQLAlchemy veritabanı işlemleri."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import Carton
from app.schemas.carton import CartonCreate, CartonStatus, CartonUpdate


class CartonRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, carton_id: int) -> Carton | None:
        return self.session.get(Carton, carton_id)

    def get_by_carton_number(self, carton_number: str) -> Carton | None:
        statement = select(Carton).where(Carton.carton_number == carton_number)
        return self.session.scalar(statement)

    def list_cartons(
        self,
        offset: int = 0,
        limit: int = 100,
        carton_status: CartonStatus | None = None,
        location_id: int | None = None,
    ) -> list[Carton]:
        statement = select(Carton).order_by(Carton.id)
        if carton_status is not None:
            statement = statement.where(Carton.status == carton_status)
        if location_id is not None:
            statement = statement.where(Carton.current_location_id == location_id)
        statement = statement.offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def create(self, data: CartonCreate, capacity_qty: int) -> Carton:
        carton = Carton(**data.model_dump(), capacity_qty=capacity_qty)
        self.session.add(carton)
        self.session.flush()
        return carton

    def update(self, carton: Carton, data: CartonUpdate) -> Carton:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(carton, field, value)

        self.session.flush()
        return carton
