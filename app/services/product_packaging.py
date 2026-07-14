"""Ürün paketleme iş kuralları ve transaction yönetimi."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalog import ProductPackaging
from app.repositories.carton_type import CartonTypeRepository
from app.repositories.product import ProductRepository
from app.repositories.product_packaging import ProductPackagingRepository
from app.schemas.product_packaging import (
    ProductPackagingCreate,
    ProductPackagingUpdate,
)


class ProductPackagingNotFoundError(Exception):
    """İstenen paketleme tanımı bulunamadığında kullanılır."""


class PackagingReferenceNotFoundError(Exception):
    """Ürün veya koli tipi foreign key kaydı bulunamadığında kullanılır."""


class InactivePackagingReferenceError(Exception):
    """Pasif ürün veya koli tipi kullanılmak istendiğinde kullanılır."""


class DuplicateProductPackagingError(Exception):
    """Ürün ve koli tipi kombinasyonu tekrarlandığında kullanılır."""


class ProductPackagingInUseError(Exception):
    """Fiziksel kolilerce kullanılan paketleme silinmek istendiğinde kullanılır."""


class ProductPackagingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ProductPackagingRepository(session)
        self.product_repository = ProductRepository(session)
        self.carton_type_repository = CartonTypeRepository(session)

    def list_packaging(
        self,
        offset: int = 0,
        limit: int = 100,
        product_id: int | None = None,
    ) -> list[ProductPackaging]:
        return self.repository.list_packaging(
            offset=offset,
            limit=limit,
            product_id=product_id,
        )

    def get_packaging(self, packaging_id: int) -> ProductPackaging:
        packaging = self.repository.get_by_id(packaging_id)
        if packaging is None:
            raise ProductPackagingNotFoundError(
                f"Product packaging {packaging_id} not found"
            )
        return packaging

    def _validate_references(self, product_id: int, carton_type_id: int) -> None:
        product = self.product_repository.get_by_id(product_id)
        if product is None:
            raise PackagingReferenceNotFoundError(f"Product {product_id} not found")
        if not product.is_active:
            raise InactivePackagingReferenceError(f"Product {product_id} is inactive")

        carton_type = self.carton_type_repository.get_by_id(carton_type_id)
        if carton_type is None:
            raise PackagingReferenceNotFoundError(
                f"Carton type {carton_type_id} not found"
            )
        if not carton_type.is_active:
            raise InactivePackagingReferenceError(
                f"Carton type {carton_type_id} is inactive"
            )

    def create_packaging(self, data: ProductPackagingCreate) -> ProductPackaging:
        self._validate_references(data.product_id, data.carton_type_id)
        existing = self.repository.get_by_product_and_carton_type(
            data.product_id,
            data.carton_type_id,
        )
        if existing is not None:
            raise DuplicateProductPackagingError(
                "Product and carton type combination already exists"
            )

        try:
            if data.is_default:
                self.repository.clear_other_defaults(data.product_id)
            packaging = self.repository.create(data)
            self.session.commit()
            self.session.refresh(packaging)
            return packaging
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateProductPackagingError(
                "Product packaging violates a database rule"
            ) from exc

    def update_packaging(
        self,
        packaging_id: int,
        data: ProductPackagingUpdate,
    ) -> ProductPackaging:
        packaging = self.get_packaging(packaging_id)
        final_product_id = (
            data.product_id
            if "product_id" in data.model_fields_set
            else packaging.product_id
        )
        final_carton_type_id = (
            data.carton_type_id
            if "carton_type_id" in data.model_fields_set
            else packaging.carton_type_id
        )
        self._validate_references(final_product_id, final_carton_type_id)

        existing = self.repository.get_by_product_and_carton_type(
            final_product_id,
            final_carton_type_id,
        )
        if existing is not None and existing.id != packaging_id:
            raise DuplicateProductPackagingError(
                "Product and carton type combination already exists"
            )

        final_is_default = (
            data.is_default
            if "is_default" in data.model_fields_set
            else packaging.is_default
        )
        try:
            if final_is_default:
                self.repository.clear_other_defaults(
                    final_product_id,
                    exclude_packaging_id=packaging_id,
                )
            packaging = self.repository.update(packaging, data)
            self.session.commit()
            self.session.refresh(packaging)
            return packaging
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateProductPackagingError(
                "Product packaging violates a database rule"
            ) from exc

    def delete_packaging(self, packaging_id: int) -> None:
        packaging = self.get_packaging(packaging_id)
        try:
            self.repository.delete(packaging)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ProductPackagingInUseError(
                f"Product packaging {packaging_id} is used by cartons"
            ) from exc
