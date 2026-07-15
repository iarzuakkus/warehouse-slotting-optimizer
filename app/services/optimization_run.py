"""Optimizasyon çalışması durum kuralları ve transaction yönetimi."""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.optimization import OptimizationRun
from app.repositories.optimization_run import OptimizationRunRepository
from app.schemas.optimization_run import (
    OptimizationRunCreate,
    OptimizationRunStatus,
    OptimizationRunUpdate,
)


class OptimizationRunNotFoundError(Exception):
    """İstenen optimizasyon çalışması bulunamadığında kullanılır."""


class OptimizationRunConflictError(Exception):
    """Durum veya sonuç kuralı güncellemeyi engellediğinde kullanılır."""


class OptimizationRunService:
    allowed_status_transitions: dict[
        OptimizationRunStatus,
        set[OptimizationRunStatus],
    ] = {
        "pending": {"running", "cancelled"},
        "running": {"completed", "failed", "cancelled"},
        "completed": set(),
        "failed": set(),
        "cancelled": set(),
    }

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = OptimizationRunRepository(session)

    def list_runs(
        self,
        offset: int = 0,
        limit: int = 100,
        run_status: OptimizationRunStatus | None = None,
    ) -> list[OptimizationRun]:
        return self.repository.list_runs(offset, limit, run_status)

    def get_run(self, run_id: int) -> OptimizationRun:
        run = self.repository.get_by_id(run_id)
        if run is None:
            raise OptimizationRunNotFoundError(
                f"Optimization run {run_id} not found"
            )
        return run

    def create_run(self, data: OptimizationRunCreate) -> OptimizationRun:
        try:
            run = self.repository.create(data)
            self.session.commit()
            self.session.refresh(run)
            return run
        except IntegrityError as exc:
            self.session.rollback()
            raise OptimizationRunConflictError(
                "Optimization run violates a database rule"
            ) from exc

    def update_run(
        self,
        run_id: int,
        data: OptimizationRunUpdate,
    ) -> OptimizationRun:
        run = self.get_run(run_id)
        target_status = data.status or run.status

        if run.status in {"completed", "failed", "cancelled"}:
            raise OptimizationRunConflictError(
                f"Optimization run cannot change after status is {run.status}"
            )
        if data.status is not None and data.status != run.status:
            allowed = self.allowed_status_transitions[run.status]
            if data.status not in allowed:
                raise OptimizationRunConflictError(
                    f"Status cannot change from {run.status} to {data.status}"
                )

        if data.objective_value is not None and target_status != "completed":
            raise OptimizationRunConflictError(
                "objective_value can only be recorded for a completed run"
            )
        if data.error_message is not None and target_status != "failed":
            raise OptimizationRunConflictError(
                "error_message can only be recorded for a failed run"
            )
        if target_status == "failed" and not data.error_message:
            raise OptimizationRunConflictError(
                "A failed run requires an error_message"
            )

        now = datetime.now(timezone.utc)
        if data.status == "running":
            run.started_at = now
        if data.status in {"completed", "failed", "cancelled"}:
            run.completed_at = now

        try:
            run = self.repository.update(run, data)
            self.session.commit()
            self.session.refresh(run)
            return run
        except IntegrityError as exc:
            self.session.rollback()
            raise OptimizationRunConflictError(
                "Optimization run update violates a database rule"
            ) from exc
