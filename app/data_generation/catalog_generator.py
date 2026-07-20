"""Sentetik ürün, koli tipi ve ambalaj tanımı üretimi."""

from dataclasses import dataclass
from decimal import Decimal
from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.algorithms.product_packaging import (
    CartonOption,
    Dimensions,
    ProductPhysicalData,
    select_carton_for_product,
)
from app.data_generation.config import SyntheticDataProfile
from app.models.catalog import CartonType, Product, ProductPackaging


PRODUCT_CATEGORIES = (
    "GIDA",
    "ICECEK",
    "TEMIZLIK",
    "KISISEL-BAKIM",
    "EV-YASAM",
    "KIRTASIYE",
    "ELEKTRONIK",
    "TEKSTIL",
    "EVCIL-HAYVAN",
    "BEBEK",
)


@dataclass(frozen=True)
class ProductPhysicalProfile:
    length_range_cm: tuple[Decimal, Decimal]
    width_range_cm: tuple[Decimal, Decimal]
    height_range_cm: tuple[Decimal, Decimal]
    density_range_kg_per_liter: tuple[Decimal, Decimal]


PRODUCT_PHYSICAL_PROFILES = {
    "GIDA": ProductPhysicalProfile(
        (Decimal("5"), Decimal("22")),
        (Decimal("4"), Decimal("16")),
        (Decimal("2"), Decimal("12")),
        (Decimal("0.25"), Decimal("0.85")),
    ),
    "ICECEK": ProductPhysicalProfile(
        (Decimal("5"), Decimal("12")),
        (Decimal("5"), Decimal("12")),
        (Decimal("12"), Decimal("35")),
        (Decimal("0.90"), Decimal("1.10")),
    ),
    "TEMIZLIK": ProductPhysicalProfile(
        (Decimal("8"), Decimal("25")),
        (Decimal("6"), Decimal("16")),
        (Decimal("12"), Decimal("35")),
        (Decimal("0.30"), Decimal("0.85")),
    ),
    "KISISEL-BAKIM": ProductPhysicalProfile(
        (Decimal("4"), Decimal("18")),
        (Decimal("3"), Decimal("12")),
        (Decimal("3"), Decimal("25")),
        (Decimal("0.20"), Decimal("0.75")),
    ),
    "EV-YASAM": ProductPhysicalProfile(
        (Decimal("12"), Decimal("45")),
        (Decimal("8"), Decimal("32")),
        (Decimal("5"), Decimal("28")),
        (Decimal("0.08"), Decimal("0.55")),
    ),
    "KIRTASIYE": ProductPhysicalProfile(
        (Decimal("3"), Decimal("22")),
        (Decimal("1"), Decimal("15")),
        (Decimal("1"), Decimal("8")),
        (Decimal("0.08"), Decimal("0.50")),
    ),
    "ELEKTRONIK": ProductPhysicalProfile(
        (Decimal("5"), Decimal("32")),
        (Decimal("4"), Decimal("24")),
        (Decimal("2"), Decimal("16")),
        (Decimal("0.18"), Decimal("0.90")),
    ),
    "TEKSTIL": ProductPhysicalProfile(
        (Decimal("10"), Decimal("40")),
        (Decimal("8"), Decimal("30")),
        (Decimal("2"), Decimal("15")),
        (Decimal("0.04"), Decimal("0.25")),
    ),
    "EVCIL-HAYVAN": ProductPhysicalProfile(
        (Decimal("18"), Decimal("70")),
        (Decimal("12"), Decimal("45")),
        (Decimal("5"), Decimal("35")),
        (Decimal("0.12"), Decimal("0.40")),
    ),
    "BEBEK": ProductPhysicalProfile(
        (Decimal("8"), Decimal("38")),
        (Decimal("6"), Decimal("28")),
        (Decimal("4"), Decimal("22")),
        (Decimal("0.08"), Decimal("0.55")),
    ),
}


@dataclass
class CatalogGenerationResult:
    products: list[Product]
    carton_types: list[CartonType]
    packaging_options: list[ProductPackaging]


def _random_decimal(
    random: Random,
    value_range: tuple[Decimal, Decimal],
    quantum: Decimal,
) -> Decimal:
    lower, upper = value_range
    return Decimal(str(random.uniform(float(lower), float(upper)))).quantize(quantum)


def _generate_product_physical_data(
    category: str,
    random: Random,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    profile = PRODUCT_PHYSICAL_PROFILES[category]
    length = _random_decimal(random, profile.length_range_cm, Decimal("0.01"))
    width = _random_decimal(random, profile.width_range_cm, Decimal("0.01"))
    height = _random_decimal(random, profile.height_range_cm, Decimal("0.01"))
    density = _random_decimal(
        random,
        profile.density_range_kg_per_liter,
        Decimal("0.001"),
    )
    volume_liters = length * width * height / Decimal("1000")
    weight = max(
        Decimal("0.001"),
        (volume_liters * density).quantize(Decimal("0.001")),
    )
    return length, width, height, weight


def generate_catalog(
    session: Session,
    profile: SyntheticDataProfile,
    random: Random,
) -> CatalogGenerationResult:
    """Katalog kayıtlarını üretir; commit işlemini çağıran katmana bırakır."""
    existing_id = session.scalar(
        select(Product.id).where(Product.sku.like("SYN-%")).limit(1)
    )
    if existing_id is not None:
        raise ValueError("Synthetic catalog data already exists")

    carton_types = [
        CartonType(
            code="SYN-CT-S",
            name="Sentetik Küçük Koli",
            inner_length_cm=Decimal("25.00"),
            inner_width_cm=Decimal("20.00"),
            inner_height_cm=Decimal("15.00"),
            outer_length_cm=Decimal("27.00"),
            outer_width_cm=Decimal("22.00"),
            outer_height_cm=Decimal("17.00"),
            max_weight_kg=Decimal("8.000"),
            is_active=True,
        ),
        CartonType(
            code="SYN-CT-M",
            name="Sentetik Orta Koli",
            inner_length_cm=Decimal("40.00"),
            inner_width_cm=Decimal("30.00"),
            inner_height_cm=Decimal("25.00"),
            outer_length_cm=Decimal("42.00"),
            outer_width_cm=Decimal("32.00"),
            outer_height_cm=Decimal("27.00"),
            max_weight_kg=Decimal("20.000"),
            is_active=True,
        ),
        CartonType(
            code="SYN-CT-L",
            name="Sentetik Büyük Koli",
            inner_length_cm=Decimal("60.00"),
            inner_width_cm=Decimal("40.00"),
            inner_height_cm=Decimal("40.00"),
            outer_length_cm=Decimal("62.00"),
            outer_width_cm=Decimal("42.00"),
            outer_height_cm=Decimal("42.00"),
            max_weight_kg=Decimal("35.000"),
            is_active=True,
        ),
        CartonType(
            code="SYN-CT-XL",
            name="Sentetik Çok Büyük Koli",
            inner_length_cm=Decimal("80.00"),
            inner_width_cm=Decimal("60.00"),
            inner_height_cm=Decimal("50.00"),
            outer_length_cm=Decimal("82.00"),
            outer_width_cm=Decimal("62.00"),
            outer_height_cm=Decimal("52.00"),
            max_weight_kg=Decimal("50.000"),
            is_active=True,
        ),
    ]
    session.add_all(carton_types)

    products: list[Product] = []
    for index in range(1, profile.product_count + 1):
        category = PRODUCT_CATEGORIES[(index - 1) % len(PRODUCT_CATEGORIES)]
        unit_length, unit_width, unit_height, unit_weight = (
            _generate_product_physical_data(category, random)
        )
        products.append(
            Product(
                sku=f"SYN-{category}-{index:06d}",
                name=f"Sentetik {category.replace('-', ' ').title()} Ürünü {index:06d}",
                unit_weight_kg=unit_weight,
                unit_length_cm=unit_length,
                unit_width_cm=unit_width,
                unit_height_cm=unit_height,
                is_active=True,
            )
        )

    session.add_all(products)
    session.flush()

    carton_options = [
        CartonOption(
            code=carton_type.code,
            max_weight_kg=carton_type.max_weight_kg,
            inner_dimensions=Dimensions(
                carton_type.inner_length_cm,
                carton_type.inner_width_cm,
                carton_type.inner_height_cm,
            ),
        )
        for carton_type in carton_types
    ]
    carton_types_by_code = {
        carton_type.code: carton_type for carton_type in carton_types
    }

    packaging_options: list[ProductPackaging] = []
    for product in products:
        selection = select_carton_for_product(
            ProductPhysicalData(
                unit_weight_kg=product.unit_weight_kg,
                dimensions=Dimensions(
                    product.unit_length_cm,
                    product.unit_width_cm,
                    product.unit_height_cm,
                ),
            ),
            carton_options,
            target_units=1,
        )
        carton_type = carton_types_by_code[selection.carton.code]
        packaging_options.append(
            ProductPackaging(
                product_id=product.id,
                carton_type_id=carton_type.id,
                units_per_carton=selection.capacity.units_per_carton,
                is_default=True,
            )
        )

    session.add_all(packaging_options)
    session.flush()
    return CatalogGenerationResult(
        products=products,
        carton_types=carton_types,
        packaging_options=packaging_options,
    )
