"""Ürün API istek ve cevap şemaları."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductBase(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    unit_weight_kg: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=3,
    )
    unit_length_cm: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=2,
    )
    unit_width_cm: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=2,
    )
    unit_height_cm: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=2,
    )
    is_active: bool = True

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_complete_dimensions(self) -> "ProductBase":
        dimensions = (
            self.unit_length_cm,
            self.unit_width_cm,
            self.unit_height_cm,
        )
        if any(value is not None for value in dimensions) and not all(
            value is not None for value in dimensions
        ):
            raise ValueError("Product dimensions must be provided together")
        return self


class ProductCreate(ProductBase):
    """Yeni ürün oluştururken kabul edilen alanlar."""


class ProductUpdate(BaseModel):
    """Ürün güncellerken isteğe bağlı kabul edilen alanlar."""

    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    unit_weight_kg: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=3,
    )
    unit_length_cm: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=2,
    )
    unit_width_cm: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=2,
    )
    unit_height_cm: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=2,
    )
    is_active: bool | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> "ProductUpdate":
        required_fields = ("sku", "name", "is_active")
        for field in required_fields:
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        dimension_fields = {
            "unit_length_cm",
            "unit_width_cm",
            "unit_height_cm",
        }
        provided_dimension_fields = dimension_fields & self.model_fields_set
        if provided_dimension_fields and provided_dimension_fields != dimension_fields:
            raise ValueError("Product dimensions must be updated together")
        if provided_dimension_fields:
            dimensions = (
                self.unit_length_cm,
                self.unit_width_cm,
                self.unit_height_cm,
            )
            if any(value is not None for value in dimensions) and not all(
                value is not None for value in dimensions
            ):
                raise ValueError("Product dimensions must be provided together")
        return self


class ProductRead(ProductBase):
    """Veritabanından dönen ürün alanları."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)
