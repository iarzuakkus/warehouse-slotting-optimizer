"""Sentetik veri üretim profili, bütünlük ve rollback testleri."""

from collections.abc import Generator

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

import app.data_generation.runner as runner_module
from app.data_generation.config import PROFILES, SyntheticDataProfile, get_profile
from app.data_generation.order_generator import build_demand_weights
from app.data_generation.runner import generate_synthetic_data
from app.db.session import engine
from app.models.catalog import CartonType, Product
from app.models.inventory import Carton, WarehouseLocation
from app.models.orders import CartonAllocation, Order, OrderLine, PickOperation


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
    session.execute(delete(Order).where(Order.order_number.like("SYN-ORD-%")))
    session.execute(delete(Carton).where(Carton.carton_number.like("SYN-CARTON-%")))
    session.execute(
        delete(WarehouseLocation).where(WarehouseLocation.aisle.like("SYN-A%"))
    )
    session.execute(delete(Product).where(Product.sku.like("SYN-%")))
    session.execute(delete(CartonType).where(CartonType.code.like("SYN-CT-%")))
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

    assert summary.product_count == tiny_profile.product_count
    assert summary.location_count == tiny_profile.location_count
    assert summary.carton_count == tiny_profile.carton_count
    assert summary.order_count == 23
    assert completed_line_count == summary.allocation_count
    assert pick_count == summary.pick_operation_count
    assert invalid_carton_count == 0


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
