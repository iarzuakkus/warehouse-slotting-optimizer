"""Koli tipi iş kuralları ve transaction yönetimi."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalog import CartonType
from app.repositories.carton_type import CartonTypeRepository
from app.schemas.carton_type import CartonTypeCreate, CartonTypeUpdate


class CartonTypeNotFoundError(Exception):
    """İstenen koli tipi bulunamadığında kullanılır."""


class DuplicateCartonTypeCodeError(Exception):
    """Aynı kodla ikinci koli tipi oluşturulmak istendiğinde kullanılır."""


class CartonTypeDimensionError(Exception):
    """Raised when inner and outer carton dimensions are inconsistent."""


class CartonTypeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CartonTypeRepository(session)

    def list_carton_types(self, offset: int = 0, limit: int = 100) -> list[CartonType]:
        return self.repository.list_carton_types(offset=offset, limit=limit)

    def get_carton_type(self, carton_type_id: int) -> CartonType:
        carton_type = self.repository.get_by_id(carton_type_id)
        if carton_type is None:
            raise CartonTypeNotFoundError(f"Carton type {carton_type_id} not found")
        return carton_type

    @staticmethod
    def _validate_dimensions(
        data: CartonTypeCreate | CartonTypeUpdate,
        current: CartonType | None = None,
    ) -> None:
        for name in ("length", "width", "height"):
            inner_field = f"inner_{name}_cm"
            outer_field = f"outer_{name}_cm"
            inner_dimension = (
                getattr(data, inner_field)
                if current is None or inner_field in data.model_fields_set
                else getattr(current, inner_field)
            )
            outer_dimension = (
                getattr(data, outer_field)
                if current is None or outer_field in data.model_fields_set
                else getattr(current, outer_field)
            )
            if outer_dimension < inner_dimension:
                raise CartonTypeDimensionError(
                    f"{outer_field} cannot be smaller than {inner_field}"
                )

    def create_carton_type(self, data: CartonTypeCreate) -> CartonType:
        normalized_data = data.model_copy(update={"code": data.code.upper()})
        self._validate_dimensions(normalized_data)

        if self.repository.get_by_code(normalized_data.code) is not None:
            raise DuplicateCartonTypeCodeError(
                f"Carton type code {normalized_data.code} already exists"
            )

        try:
            carton_type = self.repository.create(normalized_data)
            self.session.commit()
            self.session.refresh(carton_type)
            return carton_type
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateCartonTypeCodeError(
                f"Carton type code {normalized_data.code} already exists"
            ) from exc

    def update_carton_type(
        self,
        carton_type_id: int,
        data: CartonTypeUpdate,
    ) -> CartonType:
        carton_type = self.get_carton_type(carton_type_id)
        self._validate_dimensions(data, current=carton_type)

        if data.code is not None:
            normalized_code = data.code.upper()
            existing_carton_type = self.repository.get_by_code(normalized_code)
            if (
                existing_carton_type is not None
                and existing_carton_type.id != carton_type_id
            ):
                raise DuplicateCartonTypeCodeError(
                    f"Carton type code {normalized_code} already exists"
                )
            data = data.model_copy(update={"code": normalized_code})

        try:
            carton_type = self.repository.update(carton_type, data)
            self.session.commit()
            self.session.refresh(carton_type)
            return carton_type
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateCartonTypeCodeError(
                "Carton type update violates a unique rule"
            ) from exc

    def deactivate_carton_type(self, carton_type_id: int) -> CartonType:
        carton_type = self.get_carton_type(carton_type_id)
        carton_type = self.repository.deactivate(carton_type)
        self.session.commit()
        self.session.refresh(carton_type)
        return carton_type
