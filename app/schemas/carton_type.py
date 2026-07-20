"""Koli tipi API istek ve cevap şemaları."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CartonTypeBase(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=120)
    inner_length_cm: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    inner_width_cm: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    inner_height_cm: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    outer_length_cm: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    outer_width_cm: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    outer_height_cm: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    max_weight_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    is_active: bool = True

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_outer_dimensions(self) -> "CartonTypeBase":
        dimension_pairs = (
            ("length", self.inner_length_cm, self.outer_length_cm),
            ("width", self.inner_width_cm, self.outer_width_cm),
            ("height", self.inner_height_cm, self.outer_height_cm),
        )
        for name, inner_dimension, outer_dimension in dimension_pairs:
            if outer_dimension < inner_dimension:
                raise ValueError(
                    f"outer_{name}_cm cannot be smaller than inner_{name}_cm"
                )
        return self


class CartonTypeCreate(CartonTypeBase):
    """Yeni koli tipi oluştururken kabul edilen alanlar."""


class CartonTypeUpdate(BaseModel):
    """Koli tipi güncellerken isteğe bağlı kabul edilen alanlar."""

    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    inner_length_cm: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    inner_width_cm: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    inner_height_cm: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    outer_length_cm: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    outer_width_cm: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    outer_height_cm: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    max_weight_kg: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=3
    )
    is_active: bool | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "CartonTypeUpdate":
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        dimension_names = ("length", "width", "height")
        for name in dimension_names:
            inner_field = f"inner_{name}_cm"
            outer_field = f"outer_{name}_cm"
            if inner_field in self.model_fields_set and outer_field in self.model_fields_set:
                if getattr(self, outer_field) < getattr(self, inner_field):
                    raise ValueError(
                        f"{outer_field} cannot be smaller than {inner_field}"
                    )
        return self


class CartonTypeRead(CartonTypeBase):
    """Veritabanından dönen koli tipi alanları."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)
