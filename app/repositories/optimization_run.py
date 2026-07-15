"""Optimizasyon çalışması tablosu için SQLAlchemy işlemleri."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.optimization import OptimizationRun
from app.schemas.optimization_run import (
    OptimizationRunCreate,
    OptimizationRunStatus,
    OptimizationRunUpdate,
)


class OptimizationRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, run_id: int) -> OptimizationRun | None:
        return self.session.get(OptimizationRun, run_id)

    def list_runs(
        self,
        offset: int = 0,
        limit: int = 100,
        run_status: OptimizationRunStatus | None = None,
    ) -> list[OptimizationRun]:
        statement = select(OptimizationRun).order_by(
            OptimizationRun.created_at.desc(),
            OptimizationRun.id.desc(),
        )
        if run_status is not None:
            statement = statement.where(OptimizationRun.status == run_status)
        statement = statement.offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def create(self, data: OptimizationRunCreate) -> OptimizationRun:
        run = OptimizationRun(**data.model_dump())
        self.session.add(run)
        self.session.flush()
        return run

    def update(
        self,
        run: OptimizationRun,
        data: OptimizationRunUpdate,
    ) -> OptimizationRun:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(run, field, value)

        self.session.flush()
        return run
