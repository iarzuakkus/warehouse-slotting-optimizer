"""Ürün tablosu için SQLAlchemy veritabanı işlemleri."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Product
from app.schemas.product import ProductCreate, ProductUpdate


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, product_id: int) -> Product | None:
        return self.session.get(Product, product_id)

    def get_by_sku(self, sku: str) -> Product | None:
        statement = select(Product).where(Product.sku == sku)
        return self.session.scalar(statement)

    def list_products(self, offset: int = 0, limit: int = 100) -> list[Product]:
        statement = select(Product).order_by(Product.id).offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def create(self, data: ProductCreate) -> Product:
        product = Product(**data.model_dump())
        self.session.add(product)
        self.session.flush()
        return product

    def update(self, product: Product, data: ProductUpdate) -> Product:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(product, field, value)

        self.session.flush()
        return product

    def deactivate(self, product: Product) -> Product:
        product.is_active = False
        self.session.flush()
        return product
