"""Optimizasyon yerleşim önerisi tablosu için SQLAlchemy işlemleri."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.optimization import OptimizationAssignment
from app.schemas.optimization_assignment import OptimizationAssignmentCreate


class OptimizationAssignmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, assignment_id: int) -> OptimizationAssignment | None:
        return self.session.get(OptimizationAssignment, assignment_id)

    def get_by_run_and_carton(
        self,
        run_id: int,
        carton_id: int,
    ) -> OptimizationAssignment | None:
        statement = select(OptimizationAssignment).where(
            OptimizationAssignment.optimization_run_id == run_id,
            OptimizationAssignment.carton_id == carton_id,
        )
        return self.session.scalar(statement)

    def list_by_run(
        self,
        run_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[OptimizationAssignment]:
        statement = (
            select(OptimizationAssignment)
            .where(OptimizationAssignment.optimization_run_id == run_id)
            .order_by(OptimizationAssignment.id)
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def create(
        self,
        run_id: int,
        from_location_id: int | None,
        data: OptimizationAssignmentCreate,
    ) -> OptimizationAssignment:
        assignment = OptimizationAssignment(
            optimization_run_id=run_id,
            from_location_id=from_location_id,
            **data.model_dump(),
        )
        self.session.add(assignment)
        self.session.flush()
        return assignment

    def delete(self, assignment: OptimizationAssignment) -> None:
        self.session.delete(assignment)
        self.session.flush()
