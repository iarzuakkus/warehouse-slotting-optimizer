"""Ürün paketleme tablosu için SQLAlchemy veritabanı işlemleri."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.catalog import ProductPackaging
from app.schemas.product_packaging import (
    ProductPackagingCreate,
    ProductPackagingUpdate,
)


class ProductPackagingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, packaging_id: int) -> ProductPackaging | None:
        return self.session.get(ProductPackaging, packaging_id)

    def get_by_product_and_carton_type(
        self,
        product_id: int,
        carton_type_id: int,
    ) -> ProductPackaging | None:
        statement = select(ProductPackaging).where(
            ProductPackaging.product_id == product_id,
            ProductPackaging.carton_type_id == carton_type_id,
        )
        return self.session.scalar(statement)

    def list_packaging(
        self,
        offset: int = 0,
        limit: int = 100,
        product_id: int | None = None,
    ) -> list[ProductPackaging]:
        statement = select(ProductPackaging).order_by(ProductPackaging.id)
        if product_id is not None:
            statement = statement.where(ProductPackaging.product_id == product_id)
        statement = statement.offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def create(self, data: ProductPackagingCreate) -> ProductPackaging:
        packaging = ProductPackaging(**data.model_dump())
        self.session.add(packaging)
        self.session.flush()
        return packaging

    def update(
        self,
        packaging: ProductPackaging,
        data: ProductPackagingUpdate,
    ) -> ProductPackaging:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(packaging, field, value)

        self.session.flush()
        return packaging

    def clear_other_defaults(
        self,
        product_id: int,
        exclude_packaging_id: int | None = None,
    ) -> None:
        statement = (
            update(ProductPackaging)
            .where(
                ProductPackaging.product_id == product_id,
                ProductPackaging.is_default.is_(True),
            )
            .values(is_default=False)
        )
        if exclude_packaging_id is not None:
            statement = statement.where(ProductPackaging.id != exclude_packaging_id)
        self.session.execute(statement)

    def delete(self, packaging: ProductPackaging) -> None:
        self.session.delete(packaging)
        self.session.flush()
