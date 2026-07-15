"""Optimizasyon çalışması endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.optimization_run import (
    OptimizationRunCreate,
    OptimizationRunRead,
    OptimizationRunStatus,
    OptimizationRunUpdate,
)
from app.services.optimization_run import (
    OptimizationRunConflictError,
    OptimizationRunNotFoundError,
    OptimizationRunService,
)


router = APIRouter(prefix="/optimization-runs", tags=["optimization-runs"])


def get_optimization_run_service(
    db: Session = Depends(get_db),
) -> OptimizationRunService:
    return OptimizationRunService(db)


@router.get("", response_model=list[OptimizationRunRead])
def list_optimization_runs(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    run_status: OptimizationRunStatus | None = Query(default=None, alias="status"),
    service: OptimizationRunService = Depends(get_optimization_run_service),
) -> list[OptimizationRunRead]:
    return service.list_runs(offset, limit, run_status)


@router.get("/{run_id}", response_model=OptimizationRunRead)
def get_optimization_run(
    run_id: int,
    service: OptimizationRunService = Depends(get_optimization_run_service),
) -> OptimizationRunRead:
    try:
        return service.get_run(run_id)
    except OptimizationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "",
    response_model=OptimizationRunRead,
    status_code=status.HTTP_201_CREATED,
)
def create_optimization_run(
    data: OptimizationRunCreate,
    service: OptimizationRunService = Depends(get_optimization_run_service),
) -> OptimizationRunRead:
    try:
        return service.create_run(data)
    except OptimizationRunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{run_id}", response_model=OptimizationRunRead)
def update_optimization_run(
    run_id: int,
    data: OptimizationRunUpdate,
    service: OptimizationRunService = Depends(get_optimization_run_service),
) -> OptimizationRunRead:
    try:
        return service.update_run(run_id, data)
    except OptimizationRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OptimizationRunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
