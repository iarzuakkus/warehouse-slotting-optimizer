"""Koli tipi tablosu için SQLAlchemy veritabanı işlemleri."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import CartonType
from app.schemas.carton_type import CartonTypeCreate, CartonTypeUpdate


class CartonTypeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, carton_type_id: int) -> CartonType | None:
        return self.session.get(CartonType, carton_type_id)

    def get_by_code(self, code: str) -> CartonType | None:
        statement = select(CartonType).where(CartonType.code == code)
        return self.session.scalar(statement)

    def list_carton_types(self, offset: int = 0, limit: int = 100) -> list[CartonType]:
        statement = select(CartonType).order_by(CartonType.id).offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def create(self, data: CartonTypeCreate) -> CartonType:
        carton_type = CartonType(**data.model_dump())
        self.session.add(carton_type)
        self.session.flush()
        return carton_type

    def update(self, carton_type: CartonType, data: CartonTypeUpdate) -> CartonType:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(carton_type, field, value)

        self.session.flush()
        return carton_type

    def deactivate(self, carton_type: CartonType) -> CartonType:
        carton_type.is_active = False
        self.session.flush()
        return carton_type
