"""Optimizasyon yerleşim önerisi endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.optimization_assignment import (
    OptimizationAssignmentCreate,
    OptimizationAssignmentRead,
)
from app.services.optimization_assignment import (
    DuplicateOptimizationAssignmentError,
    OptimizationAssignmentConflictError,
    OptimizationAssignmentNotFoundError,
    OptimizationAssignmentReferenceNotFoundError,
    OptimizationAssignmentService,
)


router = APIRouter(
    prefix="/optimization-runs/{run_id}/assignments",
    tags=["optimization-assignments"],
)


def get_optimization_assignment_service(
    db: Session = Depends(get_db),
) -> OptimizationAssignmentService:
    return OptimizationAssignmentService(db)


@router.get("", response_model=list[OptimizationAssignmentRead])
def list_optimization_assignments(
    run_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    service: OptimizationAssignmentService = Depends(
        get_optimization_assignment_service
    ),
) -> list[OptimizationAssignmentRead]:
    try:
        return service.list_assignments(run_id, offset, limit)
    except OptimizationAssignmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{assignment_id}", response_model=OptimizationAssignmentRead)
def get_optimization_assignment(
    run_id: int,
    assignment_id: int,
    service: OptimizationAssignmentService = Depends(
        get_optimization_assignment_service
    ),
) -> OptimizationAssignmentRead:
    try:
        return service.get_assignment(run_id, assignment_id)
    except OptimizationAssignmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "",
    response_model=OptimizationAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_optimization_assignment(
    run_id: int,
    data: OptimizationAssignmentCreate,
    service: OptimizationAssignmentService = Depends(
        get_optimization_assignment_service
    ),
) -> OptimizationAssignmentRead:
    try:
        return service.create_assignment(run_id, data)
    except (
        OptimizationAssignmentNotFoundError,
        OptimizationAssignmentReferenceNotFoundError,
    ) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        DuplicateOptimizationAssignmentError,
        OptimizationAssignmentConflictError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_optimization_assignment(
    run_id: int,
    assignment_id: int,
    service: OptimizationAssignmentService = Depends(
        get_optimization_assignment_service
    ),
) -> None:
    try:
        service.delete_assignment(run_id, assignment_id)
    except OptimizationAssignmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OptimizationAssignmentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
