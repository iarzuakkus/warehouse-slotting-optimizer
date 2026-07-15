"""Koli toplama hareketi endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.pick_operation import PickOperationCreate, PickOperationRead
from app.services.pick_operation import (
    PickOperationConflictError,
    PickOperationNotFoundError,
    PickOperationReferenceNotFoundError,
    PickOperationService,
)


router = APIRouter(
    prefix=(
        "/orders/{order_id}/lines/{line_id}"
        "/allocations/{allocation_id}/picks"
    ),
    tags=["pick-operations"],
)


def get_pick_operation_service(
    db: Session = Depends(get_db),
) -> PickOperationService:
    return PickOperationService(db)


@router.get("", response_model=list[PickOperationRead])
def list_pick_operations(
    order_id: int,
    line_id: int,
    allocation_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    service: PickOperationService = Depends(get_pick_operation_service),
) -> list[PickOperationRead]:
    try:
        return service.list_operations(
            order_id,
            line_id,
            allocation_id,
            offset,
            limit,
        )
    except PickOperationReferenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{operation_id}", response_model=PickOperationRead)
def get_pick_operation(
    order_id: int,
    line_id: int,
    allocation_id: int,
    operation_id: int,
    service: PickOperationService = Depends(get_pick_operation_service),
) -> PickOperationRead:
    try:
        return service.get_operation(
            order_id,
            line_id,
            allocation_id,
            operation_id,
        )
    except (
        PickOperationNotFoundError,
        PickOperationReferenceNotFoundError,
    ) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "",
    response_model=PickOperationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_pick_operation(
    order_id: int,
    line_id: int,
    allocation_id: int,
    data: PickOperationCreate,
    service: PickOperationService = Depends(get_pick_operation_service),
) -> PickOperationRead:
    try:
        return service.create_operation(
            order_id,
            line_id,
            allocation_id,
            data,
        )
    except PickOperationReferenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PickOperationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
