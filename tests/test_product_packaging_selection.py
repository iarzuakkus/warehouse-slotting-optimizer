"""Fiziksel urun-koli eslestirme algoritmasi testleri."""

from decimal import Decimal

import pytest

from app.algorithms.product_packaging import (
    CartonOption,
    Dimensions,
    ProductPhysicalData,
    calculate_packaging_capacity,
    product_fits_carton,
    select_carton_for_product,
)


def carton(
    code: str,
    length: str,
    width: str,
    height: str,
    max_weight: str,
) -> CartonOption:
    return CartonOption(
        code=code,
        max_weight_kg=Decimal(max_weight),
        inner_dimensions=Dimensions(
            Decimal(length),
            Decimal(width),
            Decimal(height),
        ),
    )


CARTONS = [
    carton("S", "25", "20", "15", "8"),
    carton("M", "40", "30", "25", "20"),
    carton("L", "60", "40", "40", "35"),
    carton("XL", "80", "60", "50", "50"),
]


def test_product_fits_after_axis_rotation() -> None:
    assert product_fits_carton(
        Dimensions(Decimal("20"), Decimal("25"), Decimal("15")),
        CARTONS[0].inner_dimensions,
    )


def test_capacity_respects_weight_and_volume_limits() -> None:
    product = ProductPhysicalData(
        unit_weight_kg=Decimal("2"),
        dimensions=Dimensions(Decimal("10"), Decimal("10"), Decimal("10")),
    )

    capacity = calculate_packaging_capacity(product, CARTONS[1])

    assert capacity.weight_capacity == 10
    assert capacity.volume_capacity == 22
    assert capacity.units_per_carton == 10


def test_selects_smallest_carton_that_reaches_target_capacity() -> None:
    product = ProductPhysicalData(
        unit_weight_kg=Decimal("0.200"),
        dimensions=Dimensions(Decimal("5"), Decimal("5"), Decimal("5")),
    )

    selection = select_carton_for_product(product, CARTONS)

    assert selection.carton.code == "S"
    assert selection.capacity.units_per_carton == 40


def test_uses_best_capacity_when_no_carton_reaches_target() -> None:
    product = ProductPhysicalData(
        unit_weight_kg=Decimal("4"),
        dimensions=Dimensions(Decimal("30"), Decimal("20"), Decimal("10")),
    )

    selection = select_carton_for_product(product, CARTONS, target_units=50)

    assert selection.carton.code == "XL"
    assert selection.capacity.units_per_carton == 12


def test_rejects_product_that_does_not_fit_any_carton() -> None:
    product = ProductPhysicalData(
        unit_weight_kg=Decimal("1"),
        dimensions=Dimensions(Decimal("100"), Decimal("90"), Decimal("80")),
    )

    with pytest.raises(ValueError, match="does not fit"):
        select_carton_for_product(product, CARTONS)
