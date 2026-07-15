"""Sipariş satırı koli ayırma endpoint'leri."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.carton_allocation import (
    CartonAllocationCreate,
    CartonAllocationRead,
    CartonAllocationUpdate,
)
from app.services.carton_allocation import (
    CartonAllocationConflictError,
    CartonAllocationNotFoundError,
    CartonAllocationReferenceNotFoundError,
    CartonAllocationService,
    DuplicateCartonAllocationError,
)


router = APIRouter(
    prefix="/orders/{order_id}/lines/{line_id}/allocations",
    tags=["carton-allocations"],
)


def get_carton_allocation_service(
    db: Session = Depends(get_db),
) -> CartonAllocationService:
    return CartonAllocationService(db)


@router.get("", response_model=list[CartonAllocationRead])
def list_carton_allocations(
    order_id: int,
    line_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    service: CartonAllocationService = Depends(get_carton_allocation_service),
) -> list[CartonAllocationRead]:
    try:
        return service.list_allocations(order_id, line_id, offset, limit)
    except CartonAllocationReferenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{allocation_id}", response_model=CartonAllocationRead)
def get_carton_allocation(
    order_id: int,
    line_id: int,
    allocation_id: int,
    service: CartonAllocationService = Depends(get_carton_allocation_service),
) -> CartonAllocationRead:
    try:
        return service.get_allocation(order_id, line_id, allocation_id)
    except (
        CartonAllocationNotFoundError,
        CartonAllocationReferenceNotFoundError,
    ) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "",
    response_model=CartonAllocationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_carton_allocation(
    order_id: int,
    line_id: int,
    data: CartonAllocationCreate,
    service: CartonAllocationService = Depends(get_carton_allocation_service),
) -> CartonAllocationRead:
    try:
        return service.create_allocation(order_id, line_id, data)
    except CartonAllocationReferenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        CartonAllocationConflictError,
        DuplicateCartonAllocationError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{allocation_id}", response_model=CartonAllocationRead)
def update_carton_allocation(
    order_id: int,
    line_id: int,
    allocation_id: int,
    data: CartonAllocationUpdate,
    service: CartonAllocationService = Depends(get_carton_allocation_service),
) -> CartonAllocationRead:
    try:
        return service.update_allocation(order_id, line_id, allocation_id, data)
    except (
        CartonAllocationNotFoundError,
        CartonAllocationReferenceNotFoundError,
    ) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CartonAllocationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
