"""FP-Growth, ilişki kuralları ve sipariş kümesi repository testleri."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.algorithms.fp_growth import (
    generate_association_rules,
    mine_frequent_itemsets,
)
from app.db.session import engine
from app.models.catalog import Product
from app.models.orders import Order, OrderLine
from app.repositories.analysis_data import AnalysisDataRepository


@pytest.fixture
def fp_session() -> Generator[Session, None, None]:
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


def sample_transactions() -> list[set[str]]:
    return [
        {"A", "B"},
        {"A", "B"},
        {"A", "C"},
        {"A", "B", "C"},
    ]


def test_fp_growth_finds_frequent_itemsets() -> None:
    itemsets = mine_frequent_itemsets(sample_transactions(), minimum_support=0.5)
    counts = {itemset.items: itemset.support_count for itemset in itemsets}

    assert counts[("A",)] == 4
    assert counts[("A", "B")] == 3
    assert counts[("A", "C")] == 2
    assert ("B", "C") not in counts


def test_fp_growth_respects_maximum_length() -> None:
    itemsets = mine_frequent_itemsets(
        sample_transactions(),
        minimum_support=0.25,
        maximum_length=2,
    )

    assert all(len(itemset.items) <= 2 for itemset in itemsets)


def test_association_rule_calculates_confidence_and_lift() -> None:
    transactions = sample_transactions()
    itemsets = mine_frequent_itemsets(transactions, minimum_support=0.5)
    rules = generate_association_rules(
        itemsets,
        transaction_count=len(transactions),
        minimum_confidence=0.5,
    )
    rule = next(
        item
        for item in rules
        if item.antecedent == ("A",) and item.consequent == ("B",)
    )

    assert rule.support == pytest.approx(0.75)
    assert rule.confidence == pytest.approx(0.75)
    assert rule.lift == pytest.approx(1.0)


def test_fp_growth_rejects_invalid_support() -> None:
    with pytest.raises(ValueError, match="minimum_support"):
        mine_frequent_itemsets(sample_transactions(), minimum_support=0)


def test_repository_builds_completed_order_transactions(
    fp_session: Session,
) -> None:
    first_product = Product(
        sku="TEST-FP-A",
        name="FP Test Product A",
        is_active=True,
    )
    second_product = Product(
        sku="TEST-FP-B",
        name="FP Test Product B",
        is_active=True,
    )
    fp_session.add_all([first_product, second_product])
    fp_session.flush()

    completed_order = Order(
        order_number="TEST-FP-COMPLETED",
        status="completed",
    )
    pending_order = Order(
        order_number="TEST-FP-PENDING",
        status="pending",
    )
    fp_session.add_all([completed_order, pending_order])
    fp_session.flush()
    fp_session.add_all(
        [
            OrderLine(
                order_id=completed_order.id,
                product_id=first_product.id,
                ordered_qty=2,
                fulfilled_qty=2,
            ),
            OrderLine(
                order_id=completed_order.id,
                product_id=second_product.id,
                ordered_qty=1,
                fulfilled_qty=1,
            ),
            OrderLine(
                order_id=pending_order.id,
                product_id=first_product.id,
                ordered_qty=5,
                fulfilled_qty=0,
            ),
        ]
    )
    fp_session.flush()

    transactions = AnalysisDataRepository(fp_session).get_order_transactions(
        order_number_prefix="TEST-FP-"
    )

    assert transactions == [{"TEST-FP-A", "TEST-FP-B"}]
