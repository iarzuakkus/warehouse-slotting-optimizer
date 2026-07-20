"""Sentetik veri üretim profili, bütünlük ve rollback testleri."""

from collections.abc import Generator
from collections import defaultdict
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

import app.data_generation.runner as runner_module
from app.algorithms.product_packaging import (
    CartonOption,
    Dimensions,
    ProductPhysicalData,
    calculate_packaging_capacity,
    product_fits_carton,
    select_carton_for_product,
)
from app.data_generation.cleanup import delete_synthetic_data
from app.data_generation.catalog_generator import PRODUCT_PHYSICAL_PROFILES
from app.data_generation.config import PROFILES, SyntheticDataProfile, get_profile
from app.data_generation.order_generator import build_demand_weights
from app.data_generation.runner import generate_synthetic_data
from app.db.session import engine
from app.models.catalog import CartonType, Product, ProductPackaging
from app.models.inventory import Carton, WarehouseLocation, WarehouseRack
from app.models.orders import CartonAllocation, Order, OrderLine, PickOperation


def _boxes_overlap(
    first: tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal],
    second: tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal],
) -> bool:
    first_x, first_y, first_z, first_w, first_d, first_h = first
    second_x, second_y, second_z, second_w, second_d, second_h = second
    return (
        first_x < second_x + second_w
        and second_x < first_x + first_w
        and first_y < second_y + second_d
        and second_y < first_y + first_d
        and first_z < second_z + second_h
        and second_z < first_z + first_h
    )


@pytest.fixture
def generation_session() -> Generator[Session, None, None]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    # Temizlik dış transaction içinde yapılır ve test sonunda geri alınır.
    delete_synthetic_data(session)
    session.commit()

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def tiny_profile(monkeypatch: pytest.MonkeyPatch) -> SyntheticDataProfile:
    profile = SyntheticDataProfile(
        name="smoke",
        product_count=10,
        aisle_count=2,
        bays_per_aisle=2,
        levels_per_bay=2,
        slots_per_level=1,
        carton_count=20,
        historical_order_count=20,
        pending_order_count=3,
        min_lines_per_order=1,
        max_lines_per_order=4,
        batch_size=10,
    )
    monkeypatch.setitem(PROFILES, "smoke", profile)
    return profile


def test_profiles_have_expected_scale() -> None:
    smoke = get_profile("smoke")
    small = get_profile("small")

    assert smoke.location_count == 100
    assert small.product_count == 250
    assert small.location_count == 500
    assert small.historical_order_count == 10_000


def test_demand_weights_favor_popular_products() -> None:
    weights = build_demand_weights(100)

    assert len(weights) == 100
    assert weights[0] > weights[9] > weights[-1]


def test_generates_relationally_consistent_dataset(
    generation_session: Session,
    tiny_profile: SyntheticDataProfile,
) -> None:
    summary = generate_synthetic_data(
        generation_session,
        profile_name="smoke",
        seed=42,
    )

    completed_line_count = generation_session.scalar(
        select(func.count(CartonAllocation.id))
        .join(OrderLine, OrderLine.id == CartonAllocation.order_line_id)
        .join(Order, Order.id == OrderLine.order_id)
        .where(Order.order_number.like("SYN-ORD-H-%"))
    )
    pick_count = generation_session.scalar(
        select(func.count(PickOperation.id)).where(
            PickOperation.operator_reference.like("SYN-OP-%")
        )
    )
    invalid_carton_count = generation_session.scalar(
        select(func.count(Carton.id)).where(Carton.current_qty > Carton.capacity_qty)
    )
    rack_count = generation_session.scalar(
        select(func.count(WarehouseRack.id)).where(
            WarehouseRack.aisle.like("SYN-A%")
        )
    )
    incomplete_placement_count = generation_session.scalar(
        select(func.count(Carton.id)).where(
            Carton.carton_number.like("SYN-CARTON-%"),
            Carton.current_location_id.is_not(None),
            (
                Carton.position_x_cm.is_(None)
                | Carton.position_y_cm.is_(None)
                | Carton.position_z_cm.is_(None)
                | Carton.rotation_degrees.is_(None)
            ),
        )
    )
    invalid_outer_dimension_count = generation_session.scalar(
        select(func.count(CartonType.id)).where(
            CartonType.code.like("SYN-CT-%"),
            (
                (CartonType.outer_length_cm < CartonType.inner_length_cm)
                | (CartonType.outer_width_cm < CartonType.inner_width_cm)
                | (CartonType.outer_height_cm < CartonType.inner_height_cm)
            ),
        )
    )

    assert summary.product_count == tiny_profile.product_count
    assert summary.location_count == tiny_profile.location_count
    assert summary.carton_count == tiny_profile.carton_count
    assert summary.order_count == 23
    assert completed_line_count == summary.allocation_count
    assert pick_count == summary.pick_operation_count
    assert invalid_carton_count == 0
    assert rack_count == tiny_profile.aisle_count * tiny_profile.bays_per_aisle
    assert incomplete_placement_count == 0
    assert invalid_outer_dimension_count == 0


def test_generated_products_use_physically_valid_smallest_cartons(
    generation_session: Session,
    tiny_profile: SyntheticDataProfile,
) -> None:
    generate_synthetic_data(generation_session, "smoke", seed=42)
    carton_types = list(
        generation_session.scalars(
            select(CartonType)
            .where(CartonType.code.like("SYN-CT-%"))
            .order_by(CartonType.inner_length_cm)
        )
    )
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
    products = list(
        generation_session.scalars(
            select(Product)
            .where(Product.sku.like("SYN-%"))
            .options(
                selectinload(Product.packaging_options).joinedload(
                    ProductPackaging.carton_type
                )
            )
            .order_by(Product.sku)
        )
    )

    assert products
    for product in products:
        assert product.unit_weight_kg is not None and product.unit_weight_kg > 0
        assert product.unit_length_cm is not None and product.unit_length_cm > 0
        assert product.unit_width_cm is not None and product.unit_width_cm > 0
        assert product.unit_height_cm is not None and product.unit_height_cm > 0
        assert len(product.packaging_options) == 1

        category = next(
            category
            for category in PRODUCT_PHYSICAL_PROFILES
            if product.sku.startswith(f"SYN-{category}-")
        )
        physical_profile = PRODUCT_PHYSICAL_PROFILES[category]
        unit_volume_liters = (
            product.unit_length_cm
            * product.unit_width_cm
            * product.unit_height_cm
            / Decimal("1000")
        )
        effective_density = product.unit_weight_kg / unit_volume_liters
        assert (
            physical_profile.density_range_kg_per_liter[0] - Decimal("0.002")
            <= effective_density
            <= physical_profile.density_range_kg_per_liter[1] + Decimal("0.002")
        )

        packaging = product.packaging_options[0]
        product_data = ProductPhysicalData(
            unit_weight_kg=product.unit_weight_kg,
            dimensions=Dimensions(
                product.unit_length_cm,
                product.unit_width_cm,
                product.unit_height_cm,
            ),
        )
        selected_carton = packaging.carton_type
        selected_option = next(
            option for option in carton_options if option.code == selected_carton.code
        )
        capacity = calculate_packaging_capacity(product_data, selected_option)
        expected_selection = select_carton_for_product(
            product_data,
            carton_options,
            target_units=1,
        )

        assert product_fits_carton(
            product_data.dimensions,
            selected_option.inner_dimensions,
        )
        assert packaging.units_per_carton <= capacity.weight_capacity
        assert packaging.units_per_carton <= capacity.volume_capacity
        assert packaging.units_per_carton <= 100
        assert packaging.units_per_carton == capacity.units_per_carton
        assert selected_carton.code == expected_selection.carton.code
        selected_volume = selected_option.inner_dimensions.volume_cm3
        assert all(
            option.inner_dimensions.volume_cm3 >= selected_volume
            or calculate_packaging_capacity(
                product_data,
                option,
            ).units_per_carton == 0
            for option in carton_options
        )


def test_generated_cartons_stay_inside_racks_without_collisions(
    generation_session: Session,
    tiny_profile: SyntheticDataProfile,
) -> None:
    generate_synthetic_data(generation_session, "smoke", seed=42)
    cartons = list(
        generation_session.scalars(
            select(Carton)
            .where(Carton.carton_number.like("SYN-CARTON-%"))
            .options(
                joinedload(Carton.current_location).joinedload(
                    WarehouseLocation.rack
                ),
                joinedload(Carton.product_packaging).joinedload(
                    ProductPackaging.carton_type
                ),
            )
            .order_by(Carton.carton_number)
        )
    )
    boxes_by_location: dict[
        int,
        list[tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]],
    ] = defaultdict(list)

    for carton in cartons:
        if carton.current_location is None:
            continue
        assert carton.position_x_cm is not None
        assert carton.position_y_cm is not None
        assert carton.position_z_cm is not None
        assert carton.rotation_degrees in (0, 90)

        carton_type = carton.product_packaging.carton_type
        occupied_width = carton_type.outer_length_cm
        occupied_depth = carton_type.outer_width_cm
        if carton.rotation_degrees == 90:
            occupied_width, occupied_depth = occupied_depth, occupied_width
        occupied_height = carton_type.outer_height_cm
        location = carton.current_location
        assert carton.position_x_cm + occupied_width <= location.usable_width_cm
        assert carton.position_y_cm + occupied_depth <= location.usable_depth_cm
        assert carton.position_z_cm + occupied_height <= location.usable_height_cm

        box = (
            carton.position_x_cm,
            carton.position_y_cm,
            carton.position_z_cm,
            occupied_width,
            occupied_depth,
            occupied_height,
        )
        assert all(
            not _boxes_overlap(box, existing)
            for existing in boxes_by_location[location.id]
        )
        boxes_by_location[location.id].append(box)


def test_rejects_duplicate_synthetic_generation(
    generation_session: Session,
    tiny_profile: SyntheticDataProfile,
) -> None:
    generate_synthetic_data(generation_session, "smoke", seed=42)

    with pytest.raises(ValueError, match="already exists"):
        generate_synthetic_data(generation_session, "smoke", seed=42)


def test_generation_rolls_back_on_failure(
    generation_session: Session,
    tiny_profile: SyntheticDataProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_order_generation(*args: object, **kwargs: object) -> None:
        raise RuntimeError("forced generation failure")

    monkeypatch.setattr(runner_module, "generate_orders", fail_order_generation)

    with pytest.raises(RuntimeError, match="forced generation failure"):
        generate_synthetic_data(generation_session, "smoke", seed=42)

    product_count = generation_session.scalar(
        select(func.count(Product.id)).where(Product.sku.like("SYN-%"))
    )
    assert product_count == 0


def test_same_seed_produces_same_physical_carton_placements(
    generation_session: Session,
    tiny_profile: SyntheticDataProfile,
) -> None:
    generate_synthetic_data(generation_session, "smoke", seed=42)
    first_placements = list(
        generation_session.execute(
            select(
                Carton.carton_number,
                WarehouseLocation.aisle,
                WarehouseLocation.bay,
                WarehouseLocation.level,
                WarehouseLocation.slot,
                Carton.position_x_cm,
                Carton.position_y_cm,
                Carton.position_z_cm,
                Carton.rotation_degrees,
            )
            .outerjoin(
                WarehouseLocation,
                WarehouseLocation.id == Carton.current_location_id,
            )
            .where(Carton.carton_number.like("SYN-CARTON-%"))
            .order_by(Carton.carton_number)
        )
    )
    first_catalog = list(
        generation_session.execute(
            select(
                Product.sku,
                Product.unit_weight_kg,
                Product.unit_length_cm,
                Product.unit_width_cm,
                Product.unit_height_cm,
                CartonType.code,
                ProductPackaging.units_per_carton,
            )
            .join(
                ProductPackaging,
                ProductPackaging.product_id == Product.id,
            )
            .join(CartonType, CartonType.id == ProductPackaging.carton_type_id)
            .where(Product.sku.like("SYN-%"))
            .order_by(Product.sku)
        )
    )

    delete_synthetic_data(generation_session)
    generate_synthetic_data(generation_session, "smoke", seed=42)
    second_placements = list(
        generation_session.execute(
            select(
                Carton.carton_number,
                WarehouseLocation.aisle,
                WarehouseLocation.bay,
                WarehouseLocation.level,
                WarehouseLocation.slot,
                Carton.position_x_cm,
                Carton.position_y_cm,
                Carton.position_z_cm,
                Carton.rotation_degrees,
            )
            .outerjoin(
                WarehouseLocation,
                WarehouseLocation.id == Carton.current_location_id,
            )
            .where(Carton.carton_number.like("SYN-CARTON-%"))
            .order_by(Carton.carton_number)
        )
    )
    second_catalog = list(
        generation_session.execute(
            select(
                Product.sku,
                Product.unit_weight_kg,
                Product.unit_length_cm,
                Product.unit_width_cm,
                Product.unit_height_cm,
                CartonType.code,
                ProductPackaging.units_per_carton,
            )
            .join(
                ProductPackaging,
                ProductPackaging.product_id == Product.id,
            )
            .join(CartonType, CartonType.id == ProductPackaging.carton_type_id)
            .where(Product.sku.like("SYN-%"))
            .order_by(Product.sku)
        )
    )

    assert second_placements == first_placements
    assert second_catalog == first_catalog
