"""ABC algoritması ve talep repository testleri."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.algorithms.abc_analysis import ProductDemand, analyze_abc
from app.db.session import engine
from app.models.catalog import Product
from app.models.orders import Order, OrderLine
from app.repositories.analysis_data import AnalysisDataRepository


@pytest.fixture
def abc_session() -> Generator[Session, None, None]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


def test_abc_classifies_by_cumulative_demand() -> None:
    results = analyze_abc(
        [
            ProductDemand(1, "SKU-A", 80, 10),
            ProductDemand(2, "SKU-B", 15, 5),
            ProductDemand(3, "SKU-C", 5, 1),
        ]
    )

    assert [item.abc_class for item in results] == ["A", "B", "C"]
    assert results[-1].cumulative_share == pytest.approx(1.0)


def test_abc_sorts_products_by_demand() -> None:
    results = analyze_abc(
        [
            ProductDemand(1, "SKU-LOW", 10, 2),
            ProductDemand(2, "SKU-HIGH", 100, 20),
            ProductDemand(3, "SKU-MEDIUM", 50, 8),
        ]
    )

    assert [item.sku for item in results] == [
        "SKU-HIGH",
        "SKU-MEDIUM",
        "SKU-LOW",
    ]


def test_abc_excludes_zero_demand_products() -> None:
    results = analyze_abc(
        [
            ProductDemand(1, "SKU-ACTIVE", 10, 2),
            ProductDemand(2, "SKU-ZERO", 0, 0),
        ]
    )

    assert [item.sku for item in results] == ["SKU-ACTIVE"]


def test_abc_rejects_invalid_thresholds() -> None:
    with pytest.raises(ValueError, match="Thresholds"):
        analyze_abc([], a_threshold=0.95, b_threshold=0.80)


def test_repository_aggregates_completed_fulfillment(
    abc_session: Session,
) -> None:
    product = Product(
        sku="TEST-ABC-SKU",
        name="ABC Repository Test Product",
        is_active=True,
    )
    abc_session.add(product)
    abc_session.flush()

    completed_order = Order(
        order_number="TEST-ABC-COMPLETED",
        status="completed",
    )
    pending_order = Order(
        order_number="TEST-ABC-PENDING",
        status="pending",
    )
    abc_session.add_all([completed_order, pending_order])
    abc_session.flush()
    abc_session.add_all(
        [
            OrderLine(
                order_id=completed_order.id,
                product_id=product.id,
                ordered_qty=10,
                fulfilled_qty=8,
            ),
            OrderLine(
                order_id=pending_order.id,
                product_id=product.id,
                ordered_qty=20,
                fulfilled_qty=0,
            ),
        ]
    )
    abc_session.flush()

    demands = AnalysisDataRepository(abc_session).get_product_demand(
        order_number_prefix="TEST-ABC-"
    )

    assert len(demands) == 1
    assert demands[0].sku == "TEST-ABC-SKU"
    assert demands[0].total_quantity == 8
    assert demands[0].order_frequency == 1
