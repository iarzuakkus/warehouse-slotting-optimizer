"""Sipariş verisi ile FP-Growth ve ilişki kurallarını birleştiren servis."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.algorithms.fp_growth import (
    AssociationRule,
    FrequentItemset,
    generate_association_rules,
    mine_frequent_itemsets,
)
from app.repositories.analysis_data import AnalysisDataRepository


@dataclass(frozen=True)
class FPGrowthAnalysisResult:
    transaction_count: int
    itemsets: list[FrequentItemset]
    rules: list[AssociationRule]


class FPGrowthAnalysisService:
    def __init__(self, session: Session) -> None:
        self.repository = AnalysisDataRepository(session)

    def run_analysis(
        self,
        synthetic_only: bool = True,
        minimum_support: float = 0.05,
        minimum_confidence: float = 0.30,
        minimum_lift: float = 1.0,
        maximum_length: int | None = 3,
    ) -> FPGrowthAnalysisResult:
        prefix = "SYN-ORD-H-" if synthetic_only else None
        transactions = self.repository.get_order_transactions(
            order_number_prefix=prefix,
        )
        itemsets = mine_frequent_itemsets(
            transactions,
            minimum_support=minimum_support,
            maximum_length=maximum_length,
        )
        rules = (
            generate_association_rules(
                itemsets,
                transaction_count=len(transactions),
                minimum_confidence=minimum_confidence,
                minimum_lift=minimum_lift,
            )
            if transactions
            else []
        )
        return FPGrowthAnalysisResult(
            transaction_count=len(transactions),
            itemsets=itemsets,
            rules=rules,
        )
