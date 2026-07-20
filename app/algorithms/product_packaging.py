"""Urunu fiziksel olarak uygun en kucuk koli tipiyle eslestirir."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from itertools import permutations


PACKING_EFFICIENCY = Decimal("0.75")
BUSINESS_LIMIT = 100
TARGET_UNITS_PER_CARTON = 24


@dataclass(frozen=True)
class Dimensions:
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal

    def __post_init__(self) -> None:
        if min(self.length_cm, self.width_cm, self.height_cm) <= 0:
            raise ValueError("Dimensions must be positive")

    @property
    def volume_cm3(self) -> Decimal:
        return self.length_cm * self.width_cm * self.height_cm


@dataclass(frozen=True)
class ProductPhysicalData:
    unit_weight_kg: Decimal
    dimensions: Dimensions

    def __post_init__(self) -> None:
        if self.unit_weight_kg <= 0:
            raise ValueError("Product unit weight must be positive")


@dataclass(frozen=True)
class CartonOption:
    code: str
    max_weight_kg: Decimal
    inner_dimensions: Dimensions

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("Carton code cannot be empty")
        if self.max_weight_kg <= 0:
            raise ValueError("Carton maximum weight must be positive")


@dataclass(frozen=True)
class PackagingCapacity:
    weight_capacity: int
    volume_capacity: int
    units_per_carton: int


@dataclass(frozen=True)
class PackagingSelection:
    carton: CartonOption
    capacity: PackagingCapacity


def product_fits_carton(
    product: Dimensions,
    carton: Dimensions,
) -> bool:
    """Tum dik acili eksen donuslerini deneyerek tek urun sigmasini kontrol eder."""
    carton_axes = (carton.length_cm, carton.width_cm, carton.height_cm)
    product_axes = (product.length_cm, product.width_cm, product.height_cm)
    return any(
        all(product_axis <= carton_axis for product_axis, carton_axis in zip(
            orientation,
            carton_axes,
            strict=True,
        ))
        for orientation in set(permutations(product_axes))
    )


def calculate_packaging_capacity(
    product: ProductPhysicalData,
    carton: CartonOption,
    *,
    packing_efficiency: Decimal = PACKING_EFFICIENCY,
    business_limit: int = BUSINESS_LIMIT,
) -> PackagingCapacity:
    if not Decimal("0") < packing_efficiency <= Decimal("1"):
        raise ValueError("Packing efficiency must be greater than 0 and at most 1")
    if business_limit <= 0:
        raise ValueError("Business limit must be positive")
    if not product_fits_carton(product.dimensions, carton.inner_dimensions):
        return PackagingCapacity(0, 0, 0)

    weight_capacity = int(
        (carton.max_weight_kg / product.unit_weight_kg).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    volume_capacity = int(
        (
            carton.inner_dimensions.volume_cm3
            * packing_efficiency
            / product.dimensions.volume_cm3
        ).to_integral_value(rounding=ROUND_FLOOR)
    )
    return PackagingCapacity(
        weight_capacity=weight_capacity,
        volume_capacity=volume_capacity,
        units_per_carton=max(
            0,
            min(weight_capacity, volume_capacity, business_limit),
        ),
    )


def select_carton_for_product(
    product: ProductPhysicalData,
    cartons: list[CartonOption],
    *,
    packing_efficiency: Decimal = PACKING_EFFICIENCY,
    business_limit: int = BUSINESS_LIMIT,
    target_units: int = TARGET_UNITS_PER_CARTON,
) -> PackagingSelection:
    if target_units <= 0:
        raise ValueError("Target units must be positive")

    selections = [
        PackagingSelection(
            carton=carton,
            capacity=calculate_packaging_capacity(
                product,
                carton,
                packing_efficiency=packing_efficiency,
                business_limit=business_limit,
            ),
        )
        for carton in cartons
    ]
    valid = [
        selection
        for selection in selections
        if selection.capacity.units_per_carton > 0
    ]
    if not valid:
        raise ValueError("Product does not fit any available carton type")

    target_capacity = min(target_units, business_limit)
    target_matches = [
        selection
        for selection in valid
        if selection.capacity.units_per_carton >= target_capacity
    ]
    if target_matches:
        return min(
            target_matches,
            key=lambda selection: (
                selection.carton.inner_dimensions.volume_cm3,
                selection.carton.code,
            ),
        )

    return min(
        valid,
        key=lambda selection: (
            -selection.capacity.units_per_carton,
            selection.carton.inner_dimensions.volume_cm3,
            selection.carton.code,
        ),
    )
