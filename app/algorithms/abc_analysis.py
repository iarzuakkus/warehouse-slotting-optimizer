"""Ürün talebini kümülatif paylara göre A, B ve C sınıflarına ayırır."""

from dataclasses import dataclass
from typing import Literal


ABCClass = Literal["A", "B", "C"]


@dataclass(frozen=True)
class ProductDemand:
    product_id: int
    sku: str
    total_quantity: int
    order_frequency: int


@dataclass(frozen=True)
class ABCAnalysisResult:
    product_id: int
    sku: str
    total_quantity: int
    order_frequency: int
    demand_share: float
    cumulative_share: float
    abc_class: ABCClass


def analyze_abc(
    demands: list[ProductDemand],
    a_threshold: float = 0.80,
    b_threshold: float = 0.95,
) -> list[ABCAnalysisResult]:
    """Talep miktarlarını büyükten küçüğe sıralayıp ABC sınıfını hesaplar."""
    if not 0 < a_threshold < b_threshold < 1:
        raise ValueError("Thresholds must satisfy 0 < A < B < 1")
    if any(item.total_quantity < 0 for item in demands):
        raise ValueError("Demand quantities cannot be negative")

    positive_demands = [item for item in demands if item.total_quantity > 0]
    if not positive_demands:
        return []

    sorted_demands = sorted(
        positive_demands,
        key=lambda item: (-item.total_quantity, item.sku),
    )
    total_demand = sum(item.total_quantity for item in sorted_demands)
    cumulative_share = 0.0
    results: list[ABCAnalysisResult] = []

    for item in sorted_demands:
        share = item.total_quantity / total_demand
        if cumulative_share < a_threshold:
            abc_class: ABCClass = "A"
        elif cumulative_share < b_threshold:
            abc_class = "B"
        else:
            abc_class = "C"
        cumulative_share += share
        results.append(
            ABCAnalysisResult(
                product_id=item.product_id,
                sku=item.sku,
                total_quantity=item.total_quantity,
                order_frequency=item.order_frequency,
                demand_share=share,
                cumulative_share=cumulative_share,
                abc_class=abc_class,
            )
        )

    return results
