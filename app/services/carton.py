"""Fiziksel koli iş kuralları ve transaction yönetimi."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.inventory import Carton
from app.repositories.carton import CartonRepository
from app.repositories.carton_type import CartonTypeRepository
from app.repositories.product import ProductRepository
from app.repositories.product_packaging import ProductPackagingRepository
from app.repositories.warehouse_location import WarehouseLocationRepository
from app.schemas.carton import CartonCreate, CartonStatus, CartonUpdate


class CartonNotFoundError(Exception):
    """İstenen fiziksel koli bulunamadığında kullanılır."""


class DuplicateCartonNumberError(Exception):
    """Koli numarası tekrarlandığında kullanılır."""


class CartonReferenceNotFoundError(Exception):
    """Paketleme veya konum foreign key kaydı bulunamadığında kullanılır."""


class InactiveCartonReferenceError(Exception):
    """Pasif ürün, koli tipi veya konum kullanılmak istendiğinde kullanılır."""


class CartonQuantityError(Exception):
    """Koli miktarları kapasite kurallarını ihlal ettiğinde kullanılır."""


class CartonService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CartonRepository(session)
        self.packaging_repository = ProductPackagingRepository(session)
        self.product_repository = ProductRepository(session)
        self.carton_type_repository = CartonTypeRepository(session)
        self.location_repository = WarehouseLocationRepository(session)

    def list_cartons(
        self,
        offset: int = 0,
        limit: int = 100,
        carton_status: CartonStatus | None = None,
        location_id: int | None = None,
    ) -> list[Carton]:
        return self.repository.list_cartons(
            offset=offset,
            limit=limit,
            carton_status=carton_status,
            location_id=location_id,
        )

    def get_carton(self, carton_id: int) -> Carton:
        carton = self.repository.get_by_id(carton_id)
        if carton is None:
            raise CartonNotFoundError(f"Carton {carton_id} not found")
        return carton

    def _get_capacity(self, packaging_id: int) -> int:
        packaging = self.packaging_repository.get_by_id(packaging_id)
        if packaging is None:
            raise CartonReferenceNotFoundError(
                f"Product packaging {packaging_id} not found"
            )

        product = self.product_repository.get_by_id(packaging.product_id)
        carton_type = self.carton_type_repository.get_by_id(packaging.carton_type_id)
        if product is None or carton_type is None:
            raise CartonReferenceNotFoundError(
                "Product packaging references are missing"
            )
        if not product.is_active or not carton_type.is_active:
            raise InactiveCartonReferenceError(
                "Product packaging uses an inactive product or carton type"
            )
        return packaging.units_per_carton

    def _validate_location(self, location_id: int | None) -> None:
        if location_id is None:
            return
        location = self.location_repository.get_by_id(location_id)
        if location is None:
            raise CartonReferenceNotFoundError(
                f"Warehouse location {location_id} not found"
            )
        if not location.is_active:
            raise InactiveCartonReferenceError(
                f"Warehouse location {location_id} is inactive"
            )

    @staticmethod
    def _derive_status(
        current_qty: int,
        reserved_qty: int,
        requested_status: CartonStatus,
    ) -> CartonStatus:
        if requested_status == "quarantined":
            return "quarantined"
        if current_qty == 0:
            return "depleted"
        if reserved_qty > 0:
            return "reserved"
        return "available"

    @staticmethod
    def _validate_quantities(
        current_qty: int,
        reserved_qty: int,
        capacity_qty: int,
    ) -> None:
        if current_qty > capacity_qty:
            raise CartonQuantityError(
                f"current_qty cannot exceed carton capacity {capacity_qty}"
            )
        if reserved_qty > current_qty:
            raise CartonQuantityError("reserved_qty cannot exceed current_qty")

    def create_carton(self, data: CartonCreate) -> Carton:
        carton_number = data.carton_number.upper()
        if self.repository.get_by_carton_number(carton_number) is not None:
            raise DuplicateCartonNumberError(
                f"Carton number {carton_number} already exists"
            )

        capacity_qty = self._get_capacity(data.product_packaging_id)
        self._validate_location(data.current_location_id)
        self._validate_quantities(
            data.current_qty,
            data.reserved_qty,
            capacity_qty,
        )
        normalized_data = data.model_copy(
            update={
                "carton_number": carton_number,
                "status": self._derive_status(
                    data.current_qty,
                    data.reserved_qty,
                    data.status,
                ),
            }
        )

        try:
            carton = self.repository.create(normalized_data, capacity_qty)
            self.session.commit()
            self.session.refresh(carton)
            return carton
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateCartonNumberError(
                f"Carton number {carton_number} already exists"
            ) from exc

    def update_carton(self, carton_id: int, data: CartonUpdate) -> Carton:
        carton = self.get_carton(carton_id)
        final_current_qty = (
            data.current_qty
            if "current_qty" in data.model_fields_set
            else carton.current_qty
        )
        final_reserved_qty = (
            data.reserved_qty
            if "reserved_qty" in data.model_fields_set
            else carton.reserved_qty
        )
        self._validate_quantities(
            final_current_qty,
            final_reserved_qty,
            carton.capacity_qty,
        )

        requested_status = (
            data.status if "status" in data.model_fields_set else carton.status
        )
        if carton.status == "quarantined" and "status" not in data.model_fields_set:
            final_status: CartonStatus = "quarantined"
        else:
            final_status = self._derive_status(
                final_current_qty,
                final_reserved_qty,
                requested_status,
            )
        normalized_data = data.model_copy(update={"status": final_status})

        carton = self.repository.update(carton, normalized_data)
        self.session.commit()
        self.session.refresh(carton)
        return carton
