"""PostgreSQL talep verisi ile ABC algoritmasını birleştiren servis."""

from sqlalchemy.orm import Session

from app.algorithms.abc_analysis import ABCAnalysisResult, analyze_abc
from app.repositories.analysis_data import AnalysisDataRepository


class ABCAnalysisService:
    def __init__(self, session: Session) -> None:
        self.repository = AnalysisDataRepository(session)

    def run_analysis(
        self,
        synthetic_only: bool = True,
        a_threshold: float = 0.80,
        b_threshold: float = 0.95,
    ) -> list[ABCAnalysisResult]:
        prefix = "SYN-ORD-H-" if synthetic_only else None
        demands = self.repository.get_product_demand(
            order_number_prefix=prefix,
        )
        return analyze_abc(
            demands,
            a_threshold=a_threshold,
            b_threshold=b_threshold,
        )
