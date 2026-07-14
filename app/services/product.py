"""Ürün işlemlerinin iş kuralları ve transaction yönetimi."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalog import Product
from app.repositories.product import ProductRepository
from app.schemas.product import ProductCreate, ProductUpdate


class ProductNotFoundError(Exception):
    """İstenen ürün bulunamadığında kullanılır."""


class DuplicateProductSKUError(Exception):
    """Aynı SKU ile ikinci ürün oluşturulmak istendiğinde kullanılır."""


class ProductService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ProductRepository(session)

    def list_products(self, offset: int = 0, limit: int = 100) -> list[Product]:
        return self.repository.list_products(offset=offset, limit=limit)

    def get_product(self, product_id: int) -> Product:
        product = self.repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(f"Product {product_id} not found")
        return product

    def create_product(self, data: ProductCreate) -> Product:
        normalized_data = data.model_copy(update={"sku": data.sku.upper()})

        if self.repository.get_by_sku(normalized_data.sku) is not None:
            raise DuplicateProductSKUError(f"SKU {normalized_data.sku} already exists")

        try:
            product = self.repository.create(normalized_data)
            self.session.commit()
            self.session.refresh(product)
            return product
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateProductSKUError(
                f"SKU {normalized_data.sku} already exists"
            ) from exc

    def update_product(self, product_id: int, data: ProductUpdate) -> Product:
        product = self.get_product(product_id)

        if data.sku is not None:
            normalized_sku = data.sku.upper()
            existing_product = self.repository.get_by_sku(normalized_sku)
            if existing_product is not None and existing_product.id != product_id:
                raise DuplicateProductSKUError(f"SKU {normalized_sku} already exists")
            data = data.model_copy(update={"sku": normalized_sku})

        try:
            product = self.repository.update(product, data)
            self.session.commit()
            self.session.refresh(product)
            return product
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateProductSKUError("Product update violates a unique rule") from exc

    def deactivate_product(self, product_id: int) -> Product:
        product = self.get_product(product_id)
        product = self.repository.deactivate(product)
        self.session.commit()
        self.session.refresh(product)
        return product
