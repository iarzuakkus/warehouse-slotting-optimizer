"""Sentetik ürün, koli tipi ve ambalaj tanımı üretimi."""

from dataclasses import dataclass
from decimal import Decimal
from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

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


@dataclass
class CatalogGenerationResult:
    products: list[Product]
    carton_types: list[CartonType]
    packaging_options: list[ProductPackaging]


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
            max_weight_kg=Decimal("8.000"),
            is_active=True,
        ),
        CartonType(
            code="SYN-CT-M",
            name="Sentetik Orta Koli",
            inner_length_cm=Decimal("40.00"),
            inner_width_cm=Decimal("30.00"),
            inner_height_cm=Decimal("25.00"),
            max_weight_kg=Decimal("20.000"),
            is_active=True,
        ),
        CartonType(
            code="SYN-CT-L",
            name="Sentetik Büyük Koli",
            inner_length_cm=Decimal("60.00"),
            inner_width_cm=Decimal("40.00"),
            inner_height_cm=Decimal("40.00"),
            max_weight_kg=Decimal("35.000"),
            is_active=True,
        ),
        CartonType(
            code="SYN-CT-XL",
            name="Sentetik Çok Büyük Koli",
            inner_length_cm=Decimal("80.00"),
            inner_width_cm=Decimal("60.00"),
            inner_height_cm=Decimal("50.00"),
            max_weight_kg=Decimal("50.000"),
            is_active=True,
        ),
    ]
    session.add_all(carton_types)

    products: list[Product] = []
    for index in range(1, profile.product_count + 1):
        category = PRODUCT_CATEGORIES[(index - 1) % len(PRODUCT_CATEGORIES)]
        unit_weight = Decimal(str(random.uniform(0.05, 5.0))).quantize(
            Decimal("0.001")
        )
        products.append(
            Product(
                sku=f"SYN-{category}-{index:06d}",
                name=f"Sentetik {category.replace('-', ' ').title()} Ürünü {index:06d}",
                unit_weight_kg=unit_weight,
                is_active=True,
            )
        )

    session.add_all(products)
    session.flush()

    packaging_options: list[ProductPackaging] = []
    for product in products:
        carton_type = random.choice(carton_types)
        weight_capacity = int(carton_type.max_weight_kg / product.unit_weight_kg)
        units_per_carton = max(1, min(weight_capacity, 100))
        packaging_options.append(
            ProductPackaging(
                product_id=product.id,
                carton_type_id=carton_type.id,
                units_per_carton=units_per_carton,
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
