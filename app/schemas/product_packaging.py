"""Ürün paketleme API istek ve cevap şemaları."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductPackagingBase(BaseModel):
    product_id: int = Field(gt=0)
    carton_type_id: int = Field(gt=0)
    units_per_carton: int = Field(gt=0)
    is_default: bool = False


class ProductPackagingCreate(ProductPackagingBase):
    """Yeni ürün-koli paketleme tanımı oluşturur."""


class ProductPackagingUpdate(BaseModel):
    """Paketleme tanımını kısmi olarak günceller."""

    product_id: int | None = Field(default=None, gt=0)
    carton_type_id: int | None = Field(default=None, gt=0)
    units_per_carton: int | None = Field(default=None, gt=0)
    is_default: bool | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "ProductPackagingUpdate":
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ProductPackagingRead(ProductPackagingBase):
    """Veritabanından dönen ürün paketleme alanları."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
